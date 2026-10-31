import http.client
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cornea import Shell, Static, Url, Window, ready_line, run
from cornea.core import shell as shell_module
from cornea.core import window as window_module
from cornea.core.window import SimulatedWindow


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    return tmp_path


def call(
    shell: Shell, method: str, path: str, *, cookie: str = "", body: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    headers = {"Origin": shell.base_url, "Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    try:
        connection.request(
            method, path, body=json.dumps(body) if body is not None else None, headers=headers
        )
        response = connection.getresponse()
        text = response.read().decode()
        return response.status, json.loads(text) if text else {}
    finally:
        connection.close()


def sign_in(shell: Shell) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    try:
        connection.request("GET", f"/?cornea_token={shell.app.state.bootstrap_token}")
        return (connection.getresponse().getheader("Set-Cookie") or "").split(";")[0]
    finally:
        connection.close()


# ----- the simulated window -------------------------------------------------------------------


def test_simulated_window_starts_idle() -> None:
    window = SimulatedWindow("Demo")

    assert window.state() == {
        "title": "Demo",
        "maximized": False,
        "minimized": False,
        "closed": False,
        "frameless": False,
    }


def test_simulated_window_follows_the_controls() -> None:
    window = SimulatedWindow("Demo")

    window.maximize()
    assert window.state()["maximized"] is True
    window.minimize()
    assert window.state()["minimized"] is True
    window.maximize()
    assert window.state()["minimized"] is False
    window.restore()
    assert (window.state()["maximized"], window.state()["minimized"]) == (False, False)
    window.set_title("Other")
    assert window.state()["title"] == "Other"
    window.close()
    assert window.state()["closed"] is True


# ----- a headless shell -----------------------------------------------------------------------


def test_a_headless_shell_has_a_simulated_window(bundle: Path) -> None:
    shell = Shell(Static(bundle), window=None)

    assert isinstance(shell.app.state.window, SimulatedWindow)
    assert shell.app.state.window.state()["title"] == Window().title


def test_the_page_can_try_the_window_controls_in_a_browser(bundle: Path) -> None:
    with Shell(Static(bundle), window=None) as shell:
        cookie = sign_in(shell)

        assert call(shell, "GET", "/api/window", cookie=cookie)[1]["maximized"] is False
        assert call(shell, "POST", "/api/window/maximize", cookie=cookie) == (200, {"ok": True})
        assert call(shell, "GET", "/api/window", cookie=cookie)[1]["maximized"] is True
        assert call(shell, "POST", "/api/window/minimize", cookie=cookie)[0] == 200
        assert call(shell, "GET", "/api/window", cookie=cookie)[1]["minimized"] is True
        assert call(shell, "POST", "/api/window/restore", cookie=cookie)[0] == 200
        call(shell, "POST", "/api/window/title", cookie=cookie, body={"title": "Browser tab"})
        assert call(shell, "GET", "/api/window", cookie=cookie)[1]["title"] == "Browser tab"


def test_closing_a_simulated_window_keeps_the_server_running(bundle: Path) -> None:
    with Shell(Static(bundle), window=None) as shell:
        cookie = sign_in(shell)

        assert call(shell, "POST", "/api/window/close", cookie=cookie)[0] == 200

        assert call(shell, "GET", "/api/window", cookie=cookie)[1]["closed"] is True
        assert shell.running
        assert call(shell, "GET", "/health")[0] == 200


def test_window_controls_still_need_a_session_when_headless(bundle: Path) -> None:
    with Shell(Static(bundle), window=None) as shell:
        assert call(shell, "POST", "/api/window/close")[0] == 401


# ----- on_ready and the ready line ------------------------------------------------------------


def test_on_ready_is_called_once_the_server_is_serving(bundle: Path) -> None:
    shell = Shell(Static(bundle), window=None)
    seen: dict[str, Any] = {}

    def on_ready(ready: Shell) -> None:
        seen["shell"] = ready
        seen["running"] = ready.running
        seen["health"] = call(ready, "GET", "/health")[0]
        threading.Timer(0.1, ready.stop).start()

    shell.run(on_ready=on_ready)

    assert seen == {"shell": shell, "running": True, "health": 200}
    assert not shell.running


def test_on_ready_comes_before_the_window_is_shown(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    monkeypatch.setattr(window_module, "_registry_version", lambda: "1")
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace())
    monkeypatch.setattr(
        shell_module, "create_native_window", lambda *args, **kwargs: (None, SimpleNamespace())
    )
    monkeypatch.setattr(shell_module, "show_window", lambda *args: order.append("window"))

    Shell(Static(bundle)).run(on_ready=lambda shell: order.append("ready"))

    assert order == ["ready", "window"]


def test_on_ready_works_for_a_direct_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(window_module, "_registry_version", lambda: "1")
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace())
    monkeypatch.setattr(
        shell_module, "create_native_window", lambda *args, **kwargs: (None, SimpleNamespace())
    )
    monkeypatch.setattr(shell_module, "show_window", lambda *args: None)

    Shell(Url("http://localhost:5173")).run(on_ready=lambda shell: seen.append(shell.url))

    assert seen == ["http://localhost:5173"]


def test_ready_line_for_a_headless_shell(bundle: Path) -> None:
    with Shell(Static(bundle), window=None) as shell:
        line = ready_line(shell)

        assert "\n" not in line
        assert json.loads(line) == {
            "event": "ready",
            "url": shell.url,
            "port": shell.port,
            "window": False,
        }


def test_ready_line_with_a_window(bundle: Path) -> None:
    with Shell(Static(bundle)) as shell:
        message = json.loads(ready_line(shell))

        assert message["window"] is True
        assert message["url"].startswith(f"http://127.0.0.1:{message['port']}/?cornea_token=")


def test_ready_line_for_a_direct_url() -> None:
    message = json.loads(ready_line(Shell(Url("http://localhost:5173"))))

    assert message == {
        "event": "ready",
        "url": "http://localhost:5173",
        "port": None,
        "window": True,
    }


def test_nothing_is_printed_by_the_library(bundle: Path, capfd: pytest.CaptureFixture[str]) -> None:
    shell = Shell(Static(bundle), window=None)
    threading.Timer(0.2, shell.stop).start()

    shell.run()

    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_run_passes_on_ready_to_the_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    class Recorder:
        def __init__(self, *args: Any, **kwargs: Any) -> None: ...

        def run(self, on_ready: Any = None) -> None:
            calls.append(on_ready)

    monkeypatch.setattr(shell_module, "Shell", Recorder)
    callback = lambda shell: None  # noqa: E731

    run(window=None, on_ready=callback)

    assert calls == [callback]
