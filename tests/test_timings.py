import importlib.util
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from cornea import Process, Shell, Static, Timings, Window
from cornea.core import shell as shell_module
from cornea.core import window as window_module
from cornea.core.window import create_native_window
from test_window import FakeWebview

DEVSERVER = Path(__file__).with_name("devserver.py")


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>x</html>", encoding="utf-8")
    return tmp_path


def test_nothing_is_timed_before_anything_starts(bundle: Path) -> None:
    assert Shell(Static(bundle), window=None).timings == Timings()


def test_timings_default_to_none() -> None:
    timings = Timings()

    assert (
        timings.process_ready,
        timings.server_ready,
        timings.window_shown,
        timings.page_loaded,
    ) == (None, None, None, None)


def test_a_headless_start_times_the_server_only(bundle: Path) -> None:
    shell = Shell(Static(bundle), window=None)

    with shell:
        timings = shell.timings

    assert timings.server_ready is not None
    assert 0 < timings.server_ready < 10
    assert (timings.process_ready, timings.window_shown, timings.page_loaded) == (None, None, None)


def test_each_step_is_recorded_once(bundle: Path) -> None:
    shell = Shell(Static(bundle), window=None)
    with shell:
        first = shell.timings.server_ready
        shell._mark("server_ready")
        shell._mark("server_ready")

        assert shell.timings.server_ready == first


def test_marks_before_the_start_are_ignored(bundle: Path) -> None:
    shell = Shell(Static(bundle), window=None)

    shell._mark("server_ready")

    assert shell.timings.server_ready is None


def test_a_command_is_timed_before_the_server() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    source = Process(
        (sys.executable, str(DEVSERVER), "--port", str(port)),
        url=f"http://127.0.0.1:{port}",
        mode="proxy",
    )
    shell = Shell(source, window=None)

    with shell:
        timings = shell.timings

    assert timings.process_ready is not None
    assert timings.server_ready is not None
    assert timings.process_ready <= timings.server_ready


def test_the_window_reports_when_it_is_shown_and_loaded() -> None:
    webview = FakeWebview()
    seen: list[str] = []

    window, _ = create_native_window(
        webview, "http://x", Window(), lambda error: None, None, seen.append
    )
    window.events.shown.fire()
    window.events.loaded.fire()
    window.events.loaded.fire()

    assert seen == ["window_shown", "page_loaded", "page_loaded"]


def test_the_window_needs_no_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    webview = FakeWebview()

    window, _ = create_native_window(webview, "http://x", Window(), lambda error: None)

    assert len(window.events.shown.handlers) == 0


def test_a_window_run_times_the_whole_start_up(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(window_module, "_registry_version", lambda: "1")
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace())

    def create(
        webview: object,
        url: str,
        settings: object,
        on_error: object,
        app: object,
        on_event: object,
        actions: object = None,
    ) -> object:
        assert callable(on_event)
        time.sleep(0.01)
        on_event("window_shown")
        on_event("page_loaded")
        return None, SimpleNamespace(activate=lambda: None)

    monkeypatch.setattr(shell_module, "create_native_window", create)
    monkeypatch.setattr(shell_module, "show_window", lambda *args: None)
    shell = Shell(Static(bundle))
    shell.run()

    timings = shell.timings
    assert timings.server_ready is not None
    assert timings.window_shown is not None
    assert timings.page_loaded is not None
    assert timings.server_ready < timings.window_shown <= timings.page_loaded


def test_the_measuring_script_reports_a_headless_start(capsys: pytest.CaptureFixture[str]) -> None:
    path = Path(__file__).resolve().parent.parent / "scripts" / "measure_startup.py"
    spec = importlib.util.spec_from_file_location("measure_startup", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.child("headless")

    lines = capsys.readouterr().out.splitlines()
    line = next(text for text in lines if text.startswith("TIMINGS "))
    assert '"server_ready"' in line
    assert '"import"' in line
