"""The projects in examples/ must keep working, so each one is run for real, without a window."""

import http.client
import importlib.util
import json
import shutil
import socket
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from cornea import Asgi, Shell, Static, Wsgi

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Signed:
    """A signed-in browser for one running shell."""

    def __init__(self, shell: Shell) -> None:
        self.shell = shell
        connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
        connection.request("GET", f"/?cornea_token={shell.app.state.bootstrap_token}")
        self.cookie = (connection.getresponse().getheader("Set-Cookie") or "").split(";")[0]
        connection.close()

    def request(
        self, path: str, method: str = "GET", body: dict[str, Any] | None = None
    ) -> tuple[int, str, str]:
        headers = {"Cookie": self.cookie, "Origin": self.shell.base_url}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.shell.port, timeout=5)
        try:
            connection.request(
                method, path, body=json.dumps(body) if body is not None else None, headers=headers
            )
            response = connection.getresponse()
            text = response.read().decode()
            return response.status, response.getheader("Content-Type") or "", text
        finally:
            connection.close()


# ----- plain HTML -----------------------------------------------------------------------------


def test_the_plain_html_example_is_served() -> None:
    with Shell(Static(EXAMPLES / "static_html"), window=None) as shell:
        browser = Signed(shell)

        status, _, page = browser.request("/")
        assert status == 200
        assert "Hello from plain HTML" in page
        assert browser.request("/app.js")[1].startswith("text/javascript")
        assert browser.request("/style.css")[1].startswith("text/css")
        window = json.loads(browser.request("/api/window")[2])
        assert window["frameless"] is False


def test_the_plain_html_example_works_under_the_strict_policy() -> None:
    """No inline scripts or styles: the default policy would block them."""
    page = (EXAMPLES / "static_html" / "index.html").read_text(encoding="utf-8")

    assert "<script>" not in page
    assert "style=" not in page
    assert "<style" not in page


# ----- FastAPI --------------------------------------------------------------------------------


def test_the_fastapi_example_has_a_route_and_a_native_action() -> None:
    example = load("fastapi_example", EXAMPLES / "fastapi_app" / "main.py")

    with example.build_shell(headless=True) as shell:
        browser = Signed(shell)

        assert "Hello from a FastAPI backend" in browser.request("/")[2]
        status, _, body = browser.request("/api/greeting?name=Zed")
        assert (status, json.loads(body)) == (200, {"message": "Hello, Zed, from FastAPI!"})
        status, _, body = browser.request("/api/bridge/shout", "POST", {"text": "quiet"})
        assert json.loads(body) == {"available": True, "result": "QUIET"}


# ----- Flask ----------------------------------------------------------------------------------


def test_the_flask_example_is_mounted() -> None:
    pytest.importorskip("flask")
    source = Wsgi("flask_example:app", app_dir=EXAMPLES / "flask_app")

    with Shell(source, window=None) as shell:
        browser = Signed(shell)

        assert "Hello from Flask" in browser.request("/")[2]
        assert json.loads(browser.request("/hello?name=Zed")[2]) == {
            "message": "Hello, Zed, from Flask!"
        }
        assert browser.request("/static/app.js")[0] == 200
        # The API prefix stays Cornea's, even though Flask is mounted at the root.
        assert browser.request("/api/nothing")[2] == '{"error":"Not Found"}'


# ----- Django ---------------------------------------------------------------------------------


def test_the_django_example_is_mounted() -> None:
    pytest.importorskip("django")
    source = Asgi("django_example:application", app_dir=EXAMPLES / "django_app")

    with Shell(source, window=None) as shell:
        browser = Signed(shell)

        assert "Hello from Django" in browser.request("/")[2]
        assert json.loads(browser.request("/hello?name=Zed")[2]) == {
            "message": "Hello, Zed, from Django!"
        }
        assert browser.request("/app.js")[1].startswith("text/javascript")


# ----- Python entry points --------------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_the_plain_html_entry_point_is_frameless_with_an_icon() -> None:
    example = load("static_example", EXAMPLES / "static_html" / "main.py")

    with example.build_shell(headless=True) as shell:
        assert "Hello from plain HTML" in Signed(shell).request("/")[2]
    window = example.build_shell().window
    assert window is not None
    assert window.frameless is True
    assert window.icon == "icon.png"


def test_the_fastapi_entry_point_can_serve_the_app_itself() -> None:
    example = load("fastapi_mount_example", EXAMPLES / "fastapi_app" / "main.py")
    try:
        with example.build_shell(headless=True, mount=True) as shell:
            browser = Signed(shell)

            assert 'content="/greeting"' in browser.request("/")[2]
            body = json.loads(browser.request("/greeting?name=Zed")[2])
            assert body == {"message": "Hello, Zed, from FastAPI!"}
    finally:
        sys.modules.pop("main", None)


def test_the_flask_entry_point() -> None:
    pytest.importorskip("flask")
    example = load("flask_entry", EXAMPLES / "flask_app" / "main.py")

    with example.build_shell(headless=True) as shell:
        browser = Signed(shell)
        assert "Hello from Flask" in browser.request("/")[2]
        assert json.loads(browser.request("/hello?name=Zed")[2])["message"].startswith("Hello, Zed")


def test_the_django_entry_point() -> None:
    pytest.importorskip("django")
    example = load("django_entry", EXAMPLES / "django_app" / "main.py")

    with example.build_shell(headless=True) as shell:
        browser = Signed(shell)
        assert "Hello from Django" in browser.request("/")[2]
        assert json.loads(browser.request("/hello?name=Zed")[2])["message"].startswith("Hello, Zed")


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_the_node_entry_point_starts_the_server_through_cornea() -> None:
    pytest.importorskip("httpx")
    example = load("node_entry", EXAMPLES / "node_server" / "main.py")
    port = free_port()

    with example.build_shell(headless=True, mode="proxy", port=port) as shell:
        browser = Signed(shell)
        assert "Hello from Node.js" in browser.request("/")[2]
        body = json.loads(browser.request("/hello?name=Zed")[2])
        assert body["message"].startswith("Hello, Zed, from Node.js v")
    with (
        pytest.raises((ConnectionRefusedError, TimeoutError)),
        socket.create_connection(("127.0.0.1", port), timeout=1),
    ):
        pass  # the server stopped with the shell


def test_the_node_entry_point_needs_a_window_for_a_direct_address() -> None:
    example = load("node_direct", EXAMPLES / "node_server" / "main.py")

    with pytest.raises(SystemExit, match="--mode proxy"):
        example.build_shell(headless=True)
    assert example.build_shell(external=True).window is not None


def test_the_react_entry_point_serves_the_build() -> None:
    if not (EXAMPLES / "react_vite" / "dist" / "index.html").is_file():
        pytest.skip("run npm install && npm run build in examples/react_vite first")
    example = load("react_entry", EXAMPLES / "react_vite" / "main.py")

    with example.build_shell(headless=True) as shell:
        assert '<div id="root">' in Signed(shell).request("/")[2]


def test_the_react_entry_point_says_what_to_do_without_a_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    example = load("react_missing", EXAMPLES / "react_vite" / "main.py")
    monkeypatch.setattr(example, "HERE", tmp_path)

    with pytest.raises(SystemExit, match="npm install && npm run build"):
        example.build_shell(headless=True)


# ----- Vue, HTMX, Streamlit, MkDocs ------------------------------------------------------------


def test_the_vue_entry_point_serves_the_build() -> None:
    if not (EXAMPLES / "vue_vite" / "dist" / "index.html").is_file():
        pytest.skip("run npm install && npm run build in examples/vue_vite first")
    example = load("vue_entry", EXAMPLES / "vue_vite" / "main.py")

    with example.build_shell(headless=True) as shell:
        assert '<div id="app">' in Signed(shell).request("/")[2]


def test_the_htmx_example_answers_with_html_fragments() -> None:
    pytest.importorskip("jinja2")
    example = load("htmx_entry", EXAMPLES / "htmx_fastapi" / "main.py")
    try:
        with example.build_shell(headless=True) as shell:
            browser = Signed(shell)

            page = browser.request("/")[2]
            assert "Hello from HTMX" in page
            assert "<script>" not in page
            assert "javascript" in browser.request("/static/htmx.min.js")[1]
            assert "Hello, Zed, from FastAPI and HTMX!" in browser.request("/greeting?name=Zed")[2]
            assert "pressed 1 time." in browser.request("/count", "POST")[2]
    finally:
        sys.modules.pop("main", None)


def test_the_mkdocs_example_serves_the_built_site() -> None:
    pytest.importorskip("mkdocs")
    example = load("mkdocs_entry", EXAMPLES / "mkdocs_site" / "main.py")

    with example.build_shell(headless=True) as shell:
        browser = Signed(shell)

        assert "Hello from MkDocs" in browser.request("/")[2]
        assert "Edit any page" in browser.request("/guide/")[2]


def test_the_streamlit_example_runs_through_the_proxy() -> None:
    pytest.importorskip("streamlit")
    example = load("streamlit_entry", EXAMPLES / "streamlit_app" / "main.py")

    with example.build_shell(headless=True, port=free_port()) as shell:
        browser = Signed(shell)

        assert "Streamlit" in browser.request("/")[2]
        assert browser.request("/_stcore/health")[0] == 200
