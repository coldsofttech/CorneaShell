import _thread
import http.client
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from cornea import Security, Server, Shell, Static, Window, run
from cornea.core import shell as shell_module
from cornea.core.shell import _host_header


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    return tmp_path


@pytest.fixture
def shell(bundle: Path) -> Iterator[Shell]:
    instance = Shell(Static(bundle), window=None)
    try:
        yield instance
    finally:
        instance.stop()


def get(
    shell: Shell, path: str = "/", *, cookie: str | None = None, host: str | None = None
) -> tuple[http.client.HTTPResponse, bytes]:
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    if host:
        headers["Host"] = host
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        return response, response.read()
    finally:
        connection.close()


def port_is_free(port: int) -> bool:
    """Whether the port can be bound again, which means nothing is listening on it."""
    try:
        socket.create_server(("127.0.0.1", port)).close()
    except OSError:
        return False
    return True


# ----- starting, the URL and the whole sign-in flow -------------------------------------------


def test_start_binds_loopback_and_a_free_port(shell: Shell) -> None:
    shell.start()

    assert shell.running
    assert shell.port > 0
    assert shell.base_url == f"http://127.0.0.1:{shell.port}"
    assert shell.url == f"{shell.base_url}/?t={shell.app.state.bootstrap_token}"


def test_start_returns_the_shell(shell: Shell) -> None:
    assert shell.start() is shell


def test_serves_the_ui_after_the_sign_in(shell: Shell) -> None:
    shell.start()

    response, _ = get(shell, f"/?t={shell.app.state.bootstrap_token}")
    cookie = (response.getheader("Set-Cookie") or "").split(";")[0]

    assert response.status == 303
    assert response.getheader("Location") == "/"
    page, body = get(shell, "/", cookie=cookie)
    assert page.status == 200
    assert body == b"<html>shell</html>"
    assert page.getheader("Content-Security-Policy") == Security().csp


def test_the_ui_is_closed_without_the_cookie(shell: Shell) -> None:
    shell.start()

    assert get(shell, "/")[0].status == 401
    assert get(shell, "/health")[0].status == 200


def test_the_token_works_only_once(shell: Shell) -> None:
    shell.start()
    path = f"/?t={shell.app.state.bootstrap_token}"

    assert get(shell, path)[0].status == 303
    assert get(shell, path)[0].status == 403


def test_other_hosts_are_rejected(shell: Shell) -> None:
    shell.start()

    assert get(shell, "/health", host="evil.example")[0].status == 403


def test_the_token_is_not_printed(shell: Shell, capfd: pytest.CaptureFixture[str]) -> None:
    shell.start()
    token = shell.app.state.bootstrap_token

    get(shell, f"/?t={token}")
    shell.stop()

    captured = capfd.readouterr()
    assert token not in captured.out + captured.err


def test_routers_and_settings_reach_the_app(bundle: Path) -> None:
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/ping")
    def ping() -> dict[str, str]:
        return {"pong": "yes"}

    instance = Shell(
        Static(bundle), routers=[router], security=Security(api_prefix="/v1"), window=None
    )
    with instance:
        response, _ = get(instance, f"/?t={instance.app.state.bootstrap_token}")
        cookie = (response.getheader("Set-Cookie") or "").split(";")[0]

        assert get(instance, "/v1/ping", cookie=cookie)[1] == b'{"pong":"yes"}'


def test_an_explicit_port_is_used(shell: Shell) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    instance = Shell(server=Server(port=free_port), window=None)
    try:
        instance.start()

        assert instance.port == free_port
    finally:
        instance.stop()


def test_a_busy_port_is_an_error() -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        instance = Shell(server=Server(port=busy.getsockname()[1]), window=None)

        with pytest.raises(OSError):  # noqa: PT011 - the message is the platform's
            instance.start()


# ----- stopping -------------------------------------------------------------------------------


def test_stop_releases_the_port(shell: Shell) -> None:
    shell.start()
    port = shell.port
    assert not port_is_free(port)

    shell.stop()

    assert not shell.running
    assert port_is_free(port)


def test_stop_is_safe_to_repeat_and_before_start(shell: Shell) -> None:
    shell.stop()
    shell.start()
    shell.stop()
    shell.stop()


def test_context_manager_stops_even_on_errors(bundle: Path) -> None:
    instance = Shell(Static(bundle), window=None)
    ports: list[int] = []

    def use_and_fail() -> None:
        with instance:
            ports.append(instance.port)
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        use_and_fail()

    assert port_is_free(ports[0])


def test_it_cannot_be_started_twice(shell: Shell) -> None:
    shell.start()

    with pytest.raises(RuntimeError, match="already started"):
        shell.start()


def test_port_needs_a_started_server(shell: Shell) -> None:
    with pytest.raises(RuntimeError, match="not been started"):
        _ = shell.port


def test_run_returns_when_the_server_is_stopped(shell: Shell) -> None:
    worker = threading.Thread(target=shell.run)
    worker.start()
    deadline = time.monotonic() + 5
    while not shell.running and time.monotonic() < deadline:
        time.sleep(0.01)
    port = shell.port
    assert get(shell, "/health")[0].status == 200

    shell.stop()
    worker.join(5)

    assert not worker.is_alive()
    assert port_is_free(port)


def test_run_stops_on_ctrl_c(shell: Shell, monkeypatch: pytest.MonkeyPatch) -> None:
    ports: list[int] = []
    original_start = Shell.start

    def start_and_note(self: Shell) -> Shell:
        original_start(self)
        ports.append(self.port)
        # Like the user pressing Ctrl+C a moment after the server is up.
        threading.Timer(0.3, _thread.interrupt_main).start()
        return self

    monkeypatch.setattr(Shell, "start", start_and_note)

    shell.run()

    assert not shell.running
    assert port_is_free(ports[0])


# ----- startup failures -----------------------------------------------------------------------


def test_a_server_that_dies_while_starting_is_reported(
    shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(self: Any, sockets: Any = None) -> None:
        raise ValueError("cannot serve")

    monkeypatch.setattr("uvicorn.Server.run", fail)

    with pytest.raises(RuntimeError, match="stopped while starting") as caught:
        shell.start()

    assert isinstance(caught.value.__cause__, ValueError)


def test_a_server_that_never_starts_times_out(
    shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    def hang(self: Any, sockets: Any = None) -> None:
        time.sleep(0.4)

    monkeypatch.setattr("uvicorn.Server.run", hang)
    monkeypatch.setattr(shell_module, "START_TIMEOUT", 0.05)
    monkeypatch.setattr(shell_module, "STOP_TIMEOUT", 0.05)

    with pytest.raises(TimeoutError, match="did not start"):
        shell.start()


# ----- helpers --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "expected"),
    [("127.0.0.1", "127.0.0.1:80"), ("localhost", "localhost:80"), ("::1", "[::1]:80")],
)
def test_host_header_brackets_ipv6(host: str, expected: str) -> None:
    assert _host_header(host, 80) == expected


# ----- run() ----------------------------------------------------------------------------------


class Recorder:
    """Stands in for Shell to see what run() builds."""

    instances: list["Recorder"] = []  # noqa: RUF012 - test double

    def __init__(self, source: Any = None, **options: Any) -> None:
        self.source = source
        self.options = options
        self.ran = False
        Recorder.instances.append(self)

    def run(self, on_ready: Any = None) -> None:
        self.ran = True
        self.on_ready = on_ready


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> type[Recorder]:
    Recorder.instances = []
    monkeypatch.setattr(shell_module, "Shell", Recorder)
    return Recorder


def test_run_builds_a_shell_and_runs_it(recorder: type[Recorder]) -> None:
    run("web/dist", security=Security(api_prefix="/v1"))

    built = recorder.instances[0]
    assert built.ran
    assert built.source == "web/dist"
    assert built.options["security"].api_prefix == "/v1"
    assert built.options["window"] == Window()


def test_run_shorthands_change_the_window(recorder: type[Recorder]) -> None:
    run(title="My App", debug=True, window=Window(frameless=True))

    window = recorder.instances[0].options["window"]
    assert (window.title, window.debug, window.frameless) == ("My App", True, True)
    assert window.devtools_enabled


def test_run_without_a_window_rejects_window_shorthands(recorder: type[Recorder]) -> None:
    run(window=None)
    assert recorder.instances[0].options["window"] is None

    with pytest.raises(ValueError, match="need a window"):
        run(window=None, title="x")
    with pytest.raises(ValueError, match="need a window"):
        run(window=None, debug=True)
