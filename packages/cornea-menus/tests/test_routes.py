"""The routes of a running shell: what a page can read, send and fetch."""

import http.client
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from cornea import Security, Shell, Static
from cornea_menus import Item, Menu, MenuClick, Menus


def call(
    shell: Shell,
    path: str,
    method: str = "GET",
    body: object = None,
    cookie: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    headers = dict(cookie or {})
    payload = None
    if body is not None:
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if method != "GET":
        headers["Origin"] = f"http://127.0.0.1:{shell.port}"
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    data = response.read()
    result = (response.status, {k.lower(): v for k, v in response.getheaders()}, data)
    connection.close()
    return result


def session(shell: Shell) -> dict[str, str]:
    _, headers, _ = call(shell, f"/?cornea_token={shell.app.state.bootstrap_token}")
    return {"Cookie": headers["set-cookie"].split(";")[0]}


def build(tmp_path: Path, **options: Any) -> tuple[Menus, Shell]:
    (tmp_path / "index.html").write_text("<p>app</p>", encoding="utf-8")
    menus = Menus(
        [Menu("&File", [Item("file.save", "Save"), Item("file.quit", "Quit")])], **options
    )
    return menus, Shell(Static(tmp_path), window=None, extensions=[menus])


@pytest.fixture
def running(tmp_path: Path) -> Iterator[tuple[Menus, Shell, dict[str, str]]]:
    menus, shell = build(tmp_path)
    with shell:
        yield menus, shell, session(shell)


def test_the_routes_need_a_session(running: tuple[Menus, Shell, dict[str, str]]) -> None:
    _, shell, _ = running
    assert call(shell, "/api/menus")[0] == 401
    assert call(shell, "/api/menus/menus.js")[0] == 401


def test_the_page_reads_the_definition(running: tuple[Menus, Shell, dict[str, str]]) -> None:
    _, shell, cookie = running
    status, _, body = call(shell, "/api/menus", cookie=cookie)
    assert status == 200
    definition = json.loads(body)
    assert definition["theme"] == "win11"
    assert definition["bar"][0]["label"] == "&File"


def test_a_click_runs_the_python_handler(running: tuple[Menus, Shell, dict[str, str]]) -> None:
    menus, shell, cookie = running
    seen: list[MenuClick] = []
    menus.on("file.save")(seen.append)
    status, _, body = call(shell, "/api/menus/click", "POST", {"id": "file.save"}, cookie)
    assert status == 200
    assert json.loads(body)["id"] == "file.save"
    assert seen == [MenuClick("file.save", None, None)]


@pytest.mark.parametrize(
    "body", [{"id": "missing"}, {"id": "File"}, {"id": "file.save", "menu": "nope"}]
)
def test_a_click_on_something_that_cannot_be_chosen_is_a_plain_404(
    running: tuple[Menus, Shell, dict[str, str]], body: dict[str, str]
) -> None:
    _, shell, cookie = running
    status, _, data = call(shell, "/api/menus/click", "POST", body, cookie)
    assert status == 404
    assert json.loads(data) == {"error": "That menu entry cannot be chosen."}


@pytest.mark.parametrize("body", [{}, {"id": ""}, {"id": "x" * 65}, b"not json", {"id": 5}])
def test_a_malformed_click_is_refused(
    running: tuple[Menus, Shell, dict[str, str]], body: object
) -> None:
    _, shell, cookie = running
    assert call(shell, "/api/menus/click", "POST", body, cookie)[0] == 422


def test_a_click_needs_the_right_origin(running: tuple[Menus, Shell, dict[str, str]]) -> None:
    _, shell, cookie = running
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    connection.request(
        "POST",
        "/api/menus/click",
        body=b'{"id":"file.save"}',
        headers={**cookie, "Content-Type": "application/json", "Origin": "http://evil.example"},
    )
    assert connection.getresponse().status == 403


def test_the_page_defines_menus(running: tuple[Menus, Shell, dict[str, str]]) -> None:
    menus, shell, cookie = running
    new = {
        "bar": [
            {
                "type": "submenu",
                "label": "Tools",
                "items": [{"type": "item", "id": "t.run", "label": "Run"}],
            }
        ],
        "context": {},
    }
    status, _, body = call(shell, "/api/menus/definition", "POST", new, cookie)
    assert status == 200
    assert menus.entry("t.run")["label"] == "Run"
    assert json.loads(body)["version"] == menus.definition()["version"]


def test_a_bad_page_definition_is_refused_and_changes_nothing(
    running: tuple[Menus, Shell, dict[str, str]],
) -> None:
    menus, shell, cookie = running
    status, _, body = call(
        shell,
        "/api/menus/definition",
        "POST",
        {"bar": [{"type": "item", "id": "a", "label": "A"}]},
        cookie,
    )
    assert status == 422
    assert "menus" in json.loads(body)["error"]
    assert menus.entry("file.save")["label"] == "Save"


def test_a_page_definition_cannot_be_enormous(running: tuple[Menus, Shell, dict[str, str]]) -> None:
    _, shell, cookie = running
    huge = b'{"bar": [], "pad": "' + b"x" * 300_000 + b'"}'
    assert call(shell, "/api/menus/definition", "POST", huge, cookie)[0] == 413


def test_the_page_may_be_refused_the_right_to_define(tmp_path: Path) -> None:
    _, shell = build(tmp_path, page_can_define=False)
    with shell:
        status, _, _ = call(shell, "/api/menus/definition", "POST", {"bar": []}, session(shell))
    assert status == 403


@pytest.mark.parametrize("name", ["menus.js", "frame.js"])
def test_scripts_are_served_with_the_prefix_filled_in(
    running: tuple[Menus, Shell, dict[str, str]], name: str
) -> None:
    _, shell, cookie = running
    status, headers, body = call(shell, f"/api/menus/{name}", cookie=cookie)
    assert status == 200
    assert headers["content-type"].startswith("text/javascript")
    assert b"__API_PREFIX__" not in body
    assert b'"/api"' in body


def test_styles_are_served_and_unknown_themes_are_not(
    running: tuple[Menus, Shell, dict[str, str]],
) -> None:
    _, shell, cookie = running
    for path in ("/api/menus/base.css", "/api/menus/themes/xp.css"):
        status, headers, body = call(shell, path, cookie=cookie)
        assert (status, headers["content-type"].split(";")[0]) == (200, "text/css")
        assert b".cm-" in body
    for path in (
        "/api/menus/themes/vista.css",
        "/api/menus/themes/..%2Fbase.css",
        "/api/menus/nothing.js",
        "/api/menus/menus.js.map",
    ):
        assert call(shell, path, cookie=cookie)[0] == 404


def test_every_theme_has_a_stylesheet() -> None:
    from cornea_menus.model import THEMES
    from cornea_menus.routes import _asset

    for theme in THEMES:
        assert f'data-cm-theme="{theme}"'.encode() in _asset(f"themes/{theme}.css")


def test_the_frame_page_loads_no_inline_code(tmp_path: Path) -> None:
    _, shell = build(tmp_path, mode="frame", theme="xp")
    with shell:
        assert shell.url.split("?")[0].endswith("/api/menus/frame")
        status, headers, body = call(shell, shell.url.replace(f"http://127.0.0.1:{shell.port}", ""))
        assert status == 303  # the token is exchanged and the browser comes back to the same page
        status, headers, body = call(
            shell, "/api/menus/frame", cookie={"Cookie": headers["set-cookie"].split(";")[0]}
        )
    page = body.decode()
    assert status == 200
    assert "themes/xp.css" in page
    assert "<script>" not in page
    assert "style=" not in page
    assert "frame-ancestors 'self'" in headers["content-security-policy"]


def test_component_mode_keeps_frames_refused(running: tuple[Menus, Shell, dict[str, str]]) -> None:
    _, shell, cookie = running
    _, headers, _ = call(shell, "/api/menus", cookie=cookie)
    assert "frame-ancestors 'none'" in headers["content-security-policy"]


def test_only_a_frame_ancestors_none_is_relaxed_for_frame_mode(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    custom = "default-src 'self'; frame-ancestors https://example.test"
    kept = Shell(
        Static(tmp_path),
        window=None,
        security=Security(csp=custom),
        extensions=[Menus(mode="frame")],
    )
    assert kept.security.csp == custom
    relaxed = Shell(Static(tmp_path), window=None, extensions=[Menus(mode="frame")])
    assert "frame-ancestors 'self'" in relaxed.security.csp
    assert "frame-ancestors 'none'" not in relaxed.security.csp
