"""The projects in examples/ must keep working, so each one is run for real, without a window."""

import http.client
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
import time
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
        connection.request("GET", f"/?t={shell.app.state.bootstrap_token}")
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


# ----- Node.js --------------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_the_node_example_serves_its_own_page() -> None:
    node = shutil.which("node")
    assert node is not None
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen(
        [node, str(EXAMPLES / "node_server" / "server.js")],
        env={
            "PORT": str(port),
            "PATH": str(Path(sys.executable).parent),
            "SystemRoot": "C:\\Windows",
        },
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert f"http://127.0.0.1:{port}" in process.stdout.readline()
        deadline = time.time() + 5
        while True:
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request("GET", "/hello?name=Zed")
                body = json.loads(connection.getresponse().read())
                break
            except OSError:
                assert time.time() < deadline
                time.sleep(0.1)
    finally:
        process.terminate()
        process.wait(timeout=10)

    assert body["message"].startswith("Hello, Zed, from Node.js v")
