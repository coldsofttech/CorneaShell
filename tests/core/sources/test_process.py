import http.client
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from cornea import Process, Server, Shell, Url, create_app
from cornea.core import shell as shell_module
from cornea.core.sources.process import OUTPUT_LINES, ProcessRunner
from cornea.core.window import window as window_module

DEVSERVER = Path(__file__).resolve().parents[2] / "devserver.py"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def port_is_free(port: int) -> bool:
    try:
        socket.create_server(("127.0.0.1", port)).close()
    except OSError:
        return False
    return True


def wait_until_free(port: int, seconds: float = 8) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if port_is_free(port):
            return True
        time.sleep(0.1)
    return False


def command(port: int, *extra: str) -> tuple[str, ...]:
    return (sys.executable, str(DEVSERVER), "--port", str(port), *extra)


def source(port: int, *extra: str, **options: object) -> Process:
    return Process(command(port, *extra), url=f"http://127.0.0.1:{port}", **options)  # type: ignore[arg-type]


def get(port: int, path: str = "/") -> bytes:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        return connection.getresponse().read()
    finally:
        connection.close()


# ----- the source -----------------------------------------------------------------------------


def test_a_process_source_describes_a_command_and_an_address() -> None:
    process = Process("npm run dev", url="http://localhost:5173", cwd="web", mode="proxy")

    assert (process.command, process.url, process.cwd, process.mode) == (
        "npm run dev",
        "http://localhost:5173",
        "web",
        "proxy",
    )
    assert process.timeout == 30.0


@pytest.mark.parametrize("empty", ["", "   ", ()])
def test_the_command_must_not_be_empty(empty: object) -> None:
    with pytest.raises(ValueError, match="command must not be empty"):
        Process(empty, url="http://localhost:5173")  # type: ignore[arg-type]


def test_the_address_and_mode_are_checked_like_a_url() -> None:
    with pytest.raises(ValueError, match="http or https"):
        Process("x", url="localhost:5173")
    with pytest.raises(ValueError, match="mode must be"):
        Process("x", url="http://localhost:5173", mode="other")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timeout"):
        Process("x", url="http://localhost:5173", timeout=0)


def test_create_app_leaves_process_sources_to_the_shell() -> None:
    with pytest.raises(ValueError, match="started by Shell"):
        create_app(Process("x", url="http://localhost:5173"))


# ----- the runner -----------------------------------------------------------------------------


def test_start_waits_until_the_address_answers_and_stop_frees_it() -> None:
    port = free_port()
    runner = ProcessRunner(source(port))

    runner.start()
    try:
        assert runner.running
        assert get(port) == b"dev server page"
    finally:
        runner.stop()

    assert not runner.running
    assert wait_until_free(port)


def test_a_string_command_runs_through_the_shell() -> None:
    port = free_port()
    text = f'"{sys.executable}" "{DEVSERVER}" --port {port}'
    runner = ProcessRunner(Process(text, url=f"http://127.0.0.1:{port}"))

    runner.start()
    try:
        assert get(port) == b"dev server page"
    finally:
        runner.stop()


def test_the_command_runs_in_the_given_folder(tmp_path: Path) -> None:
    port = free_port()
    runner = ProcessRunner(source(port, "--print-cwd", cwd=tmp_path))

    runner.start()
    try:
        deadline = time.monotonic() + 5
        while "cwd=" not in runner.output_tail and time.monotonic() < deadline:
            time.sleep(0.05)
        assert tmp_path.name in runner.output_tail
    finally:
        runner.stop()


def test_stopping_ends_everything_the_command_started() -> None:
    port = free_port()
    marker = Path(__file__).with_name("child-port.tmp")
    runner = ProcessRunner(source(port, "--child-port-file", str(marker)))

    runner.start()
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        child_port = int(marker.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 5
        while port_is_free(child_port) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not port_is_free(child_port)
    finally:
        runner.stop()
        marker.unlink(missing_ok=True)

    assert wait_until_free(port)
    assert wait_until_free(child_port)


def test_a_command_that_exits_before_it_listens_is_explained() -> None:
    port = free_port()
    runner = ProcessRunner(source(port, "--exit-code", "3"))

    with pytest.raises(RuntimeError, match="exited with code 3") as caught:
        runner.start()

    assert "failing on purpose" in str(caught.value)
    assert not runner.running


def test_a_command_that_never_listens_times_out() -> None:
    port = free_port()
    runner = ProcessRunner(source(port, "--never-listen", timeout=1))

    with pytest.raises(TimeoutError, match="did not answer within 1 seconds") as caught:
        runner.start()

    assert "starting up..." in str(caught.value)
    assert not runner.running


def test_a_busy_address_is_reported_before_anything_starts() -> None:
    with socket.create_server(("127.0.0.1", 0)) as busy:
        port = busy.getsockname()[1]
        runner = ProcessRunner(source(port))

        with pytest.raises(RuntimeError, match="already listening"):
            runner.start()

        assert not runner.running


def test_a_missing_program_is_a_clear_error() -> None:
    port = free_port()
    runner = ProcessRunner(Process(("no-such-program-xyz",), url=f"http://127.0.0.1:{port}"))

    with pytest.raises(RuntimeError, match="could not start"):
        runner.start()


def test_a_shell_command_that_fails_is_reported_with_its_output() -> None:
    port = free_port()
    runner = ProcessRunner(Process("no-such-program-xyz", url=f"http://127.0.0.1:{port}"))

    with pytest.raises(RuntimeError, match="exited with code"):
        runner.start()


def test_only_the_last_lines_of_output_are_kept() -> None:
    port = free_port()
    runner = ProcessRunner(source(port, "--noisy"))

    runner.start()
    try:
        deadline = time.monotonic() + 5
        while "line 199" not in runner.output_tail and time.monotonic() < deadline:
            time.sleep(0.05)
        lines = runner.output_tail.splitlines()
        assert len(lines) == OUTPUT_LINES
        # the server may append its own noise (e.g. a reset-connection traceback) after the output
        assert "line 199" in lines
        assert "line 0" not in lines
    finally:
        runner.stop()


def test_stop_is_safe_to_repeat_and_before_start() -> None:
    port = free_port()
    runner = ProcessRunner(source(port))

    runner.stop()
    runner.start()
    runner.stop()
    runner.stop()


def test_it_cannot_be_started_twice() -> None:
    port = free_port()
    runner = ProcessRunner(source(port))
    runner.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            runner.start()
    finally:
        runner.stop()


# ----- the shell ------------------------------------------------------------------------------


def test_a_proxied_process_is_served_and_stopped_with_the_shell() -> None:
    port = free_port()
    shell = Shell(source(port, mode="proxy"), window=None)

    with shell:
        connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=10)
        connection.request("GET", f"/?cornea_token={shell.app.state.bootstrap_token}")
        cookie = (connection.getresponse().getheader("Set-Cookie") or "").split(";")[0]
        connection.close()
        connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=10)
        connection.request("GET", "/", headers={"Cookie": cookie})
        assert connection.getresponse().read() == b"dev server page"
        connection.close()
        assert not port_is_free(port)

    assert wait_until_free(port)


def test_a_failing_command_means_the_shell_does_not_start() -> None:
    port = free_port()
    shell = Shell(source(port, "--exit-code", "2", mode="proxy"), window=None)

    with pytest.raises(RuntimeError, match="exited with code 2"):
        shell.start()

    assert not shell.running


def test_the_command_is_stopped_when_the_server_cannot_start() -> None:
    port = free_port()
    with socket.create_server(("127.0.0.1", 0)) as busy:
        taken = busy.getsockname()[1]
        shell = Shell(source(port, mode="proxy"), server=Server(port=taken), window=None)

        with pytest.raises(OSError):  # noqa: PT011 - the message is the platform's
            shell.start()

    assert wait_until_free(port)


def test_a_direct_process_is_started_for_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    port = free_port()
    seen: dict[str, object] = {}
    monkeypatch.setattr(window_module, "_registry_version", lambda: "1")
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace())
    monkeypatch.setattr(
        shell_module, "create_native_window", lambda *a, **k: (None, SimpleNamespace())
    )
    monkeypatch.setattr(shell_module, "show_window", lambda *a: seen.setdefault("shown", True))
    shell = Shell(source(port, mode="direct"))

    def on_ready(ready: Shell) -> None:
        seen["address"] = ready.url
        seen["answers"] = get(port)

    shell.run(on_ready=on_ready)

    assert shell.is_direct
    assert seen == {
        "address": f"http://127.0.0.1:{port}",
        "answers": b"dev server page",
        "shown": True,
    }
    assert wait_until_free(port)


def test_a_process_with_a_url_source_is_not_confused(tmp_path: Path) -> None:
    shell = Shell(Url("http://localhost:5173", mode="proxy"), window=None)

    assert shell._runner is None
