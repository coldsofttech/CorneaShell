import http.client
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from cornea import Bridge, Shell, Static, Window
from cornea.core import shell as shell_module
from cornea.core.window import window as window_module
from cornea.core.window.window import SimulatedWindow, Unavailable, check_window_path
from window_fakes import FakeWebview, FakeWebViewOptions, FakeWindow


@pytest.fixture
def webview(monkeypatch: pytest.MonkeyPatch) -> FakeWebview:
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(window_module, "_registry_version", lambda: "130.0.1")
    monkeypatch.setattr(window_module, "_invoke", lambda native, function: function())
    monkeypatch.setattr(window_module, "CLOSE_DELAY", 0)
    monkeypatch.setattr(shell_module, "require_windows", lambda: None)  # runs on any system
    FakeWebViewOptions.fail = False
    return fake


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    return tmp_path


def post(
    shell: Shell, path: str, cookie: str, body: dict[str, Any] | None = None, window: str = ""
) -> tuple[int, dict[str, Any]]:
    headers = {"Origin": shell.base_url, "Content-Type": "application/json", "Cookie": cookie}
    if window:
        headers["X-Cornea-Window"] = window
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    try:
        connection.request("POST", path, body=json.dumps(body or {}), headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode() or "{}")
    finally:
        connection.close()


def sign_in(shell: Shell) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    try:
        connection.request("GET", f"/?cornea_token={shell.app.state.bootstrap_token}")
        return (connection.getresponse().getheader("Set-Cookie") or "").split(";")[0]
    finally:
        connection.close()


@pytest.mark.parametrize("path", ["/", "/settings", "/a/b?x=1#top"])
def test_paths_on_this_app_are_allowed(path: str) -> None:
    assert check_window_path(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "",
        "settings",
        "//evil.example/",
        "/\\evil",
        "http://evil.example/",
        "/a\nb",
        "/?cornea_window=x",
        5,
    ],
)
def test_other_addresses_are_refused(path: object) -> None:
    with pytest.raises(ValueError, match=r"path|window"):
        check_window_path(path)


def test_without_a_window_there_is_nothing_to_open_from() -> None:
    with pytest.raises(RuntimeError, match="no window"):
        Shell(window=None).open_window("/x")
    with pytest.raises(Unavailable):
        SimulatedWindow("t").open_window("/x")


def test_a_child_window_is_served_by_the_same_server(webview: FakeWebview, bundle: Path) -> None:
    shell = Shell(Static(bundle), loading=None, window=Window(title="Main", icon=None))
    seen: dict[str, Any] = {}

    def while_open(window: FakeWindow) -> None:
        if len(webview.windows) > 1:
            return
        child_id = shell.open_window("/settings?tab=1", title="Settings", size=(500, 400))
        child = webview.windows[1]
        seen.update(
            base=shell.base_url,
            id=child_id,
            url=child.url,
            title=child.title,
            options=child.options,
        )
        seen["open"] = shell.windows
        child.events.closed.fire()
        seen["after"] = shell.windows

    webview.while_open = while_open
    shell.run()

    assert seen["url"] == f"{seen['base']}/settings?tab=1&cornea_window={seen['id']}"
    assert seen["title"] == "Settings"
    assert (seen["options"]["width"], seen["options"]["height"]) == (500, 400)
    assert seen["open"] == [seen["id"]]
    assert seen["after"] == []


def test_a_named_window_is_reused_and_the_number_is_limited(
    webview: FakeWebview, bundle: Path
) -> None:
    shell = Shell(Static(bundle), loading=None, window=Window(max_child_windows=2))
    seen: dict[str, Any] = {}

    def while_open(window: FakeWindow) -> None:
        if len(webview.windows) > 1:
            return
        first = shell.open_window("/a", name="prefs")
        seen["same"] = shell.open_window("/a", name="prefs") == first
        seen["count"] = len(webview.windows)
        seen["shown"] = "show" in webview.windows[1].calls
        shell.open_window("/b")
        with pytest.raises(ValueError, match="already open"):
            shell.open_window("/c")
        with pytest.raises(ValueError, match="path"):
            shell.open_window("https://evil.example/")

    webview.while_open = while_open
    shell.run()
    assert seen == {"same": True, "count": 2, "shown": True}


def test_closing_the_main_window_closes_the_children(webview: FakeWebview, bundle: Path) -> None:
    shell = Shell(Static(bundle), loading=None)

    def while_open(window: FakeWindow) -> None:
        if len(webview.windows) > 1:
            return
        shell.open_window("/a")
        window.events.closed.fire()
        time.sleep(0.2)

    webview.while_open = while_open
    shell.run()
    assert "destroy" in webview.windows[1].calls


def run_page_open(webview: FakeWebview, bundle: Path, allowed: bool) -> dict[str, Any]:
    results: dict[str, Any] = {}
    shell = Shell(Static(bundle), loading=None, bridge=Bridge(windows=allowed))

    def while_open(window: FakeWindow) -> None:
        if results:  # the child it opened is visited too
            return
        cookie = sign_in(shell)
        results["open"] = post(
            shell, "/api/bridge/open_window", cookie, {"path": "/pop", "name": "p"}
        )
        results["bad"] = post(shell, "/api/bridge/open_window", cookie, {"path": "//evil.example"})

    webview.while_open = while_open
    shell.run()
    return results


def test_the_page_cannot_open_windows_unless_allowed(webview: FakeWebview, bundle: Path) -> None:
    assert run_page_open(webview, bundle, False)["open"][0] == 404


def test_the_page_can_open_windows_when_allowed(webview: FakeWebview, bundle: Path) -> None:
    results = run_page_open(webview, bundle, True)
    assert results["open"][0] == 200, results
    assert results["open"][1]["result"]["id"]
    assert results["bad"][0] == 422


def test_window_routes_act_on_the_window_that_calls(webview: FakeWebview, bundle: Path) -> None:
    shell = Shell(Static(bundle), loading=None)
    results: dict[str, Any] = {}

    def while_open(window: FakeWindow) -> None:
        if len(webview.windows) > 1:
            return
        child_id = shell.open_window("/a")
        cookie = sign_in(shell)
        results["child"] = post(shell, "/api/window/minimize", cookie, window=child_id)
        results["unknown"] = post(shell, "/api/window/maximize", cookie, window="nope")

    webview.while_open = while_open
    shell.run()
    assert results["child"] == (200, {"ok": True})
    assert webview.windows[1].calls == ["minimize"]
    assert webview.windows[0].calls == ["maximize"]  # an unknown id falls back to the main window


def test_a_direct_url_cannot_open_windows(webview: FakeWebview) -> None:
    shell = Shell("https://example.com", loading=None)

    def while_open(window: FakeWindow) -> None:
        with pytest.raises(RuntimeError, match="direct URL"):
            shell.open_window("/a")

    webview.while_open = while_open
    shell.run()
