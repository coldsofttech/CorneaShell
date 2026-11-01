"""Logging: quiet by default, readable when asked, and never showing the start-up token."""

import http.client
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from cornea import Shell, Static, Window, configure_logging
from cornea.cli import app
from cornea.core import shell as shell_module
from cornea.core.logs import Logs
from cornea.core.window import window as window_module

runner = CliRunner()
TOKEN = "s3cret-token-value"  # noqa: S105


class Calls:
    """Stands in for run(): the command line only has to get as far as calling it."""

    def __call__(self, *args: object, **kwargs: object) -> None:
        return None


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    recorded = Calls()
    monkeypatch.setattr("cornea.cli.commands.run_shell", recorded)
    return recorded


@pytest.fixture(autouse=True)
def restore_cornea_logging(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Undo configure_logging after each test.

    A command such as ``open --debug`` configures logging for real, and its handler would
    otherwise outlive the test and write to a stream that is already closed.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))  # where debug logs go
    logger = logging.getLogger("cornea")
    level, propagate = logger.level, logger.propagate
    yield
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(level)
    logger.propagate = propagate


@pytest.fixture
def clean_logger() -> logging.Logger:
    """The cornea logger, restored after each test by the fixture above."""
    return logging.getLogger("cornea")


def test_nothing_is_configured_until_asked(clean_logger: logging.Logger) -> None:
    assert clean_logger.handlers == []


def test_the_level_decides_what_stderr_shows(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("info")
    logger = logging.getLogger("cornea.test")

    logger.debug("too detailed")
    logger.info("worth knowing")

    shown = capsys.readouterr().err
    assert "worth knowing" in shown
    assert "too detailed" not in shown


def test_the_file_gets_every_message(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "cornea.log"
    configure_logging("error", file=log)

    logging.getLogger("cornea.test").debug("a detail")

    assert "a detail" in log.read_text(encoding="utf-8")


def test_the_start_up_token_is_hidden(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "cornea.log"
    configure_logging("debug", file=log)

    logging.getLogger("cornea.test").debug("opened http://x/?cornea_token=%s&a=1", TOKEN)

    assert TOKEN not in capsys.readouterr().err
    written = log.read_text(encoding="utf-8")
    assert TOKEN not in written
    assert "cornea_token=<hidden>&a=1" in written


def test_calling_it_again_replaces_the_setup(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("debug")
    configure_logging("debug")

    logging.getLogger("cornea.test").debug("once")

    assert capsys.readouterr().err.count("once") == 1


def test_an_unknown_level_is_an_error() -> None:
    with pytest.raises(ValueError, match="level must be one of"):
        configure_logging("loud")  # type: ignore[arg-type]


def test_a_refused_request_is_logged_without_its_token(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    (tmp_path / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    caplog.set_level(logging.DEBUG, logger="cornea")
    with Shell(Static(tmp_path), window=None) as shell:
        connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
        connection.request("GET", f"/?cornea_token={TOKEN}")
        assert connection.getresponse().status == 403
        connection.close()

    text = caplog.text
    assert "Refused GET /" in text
    assert "start-up token" in text
    assert TOKEN not in text


def test_start_up_steps_are_logged(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    caplog.set_level(logging.DEBUG, logger="cornea")

    with Shell(Static(tmp_path), window=None):
        pass

    assert "Start-up step server_ready" in caplog.text
    assert "Serving on http://127.0.0.1:" in caplog.text


# ----- the command line ------------------------------------------------------------------------


def test_debug_turns_on_debug_logging(calls: Calls, clean_logger: logging.Logger) -> None:
    result = runner.invoke(app, ["open", "web", "--debug"])

    assert result.exit_code == 0
    assert clean_logger.level == logging.DEBUG


def test_log_level_overrides_debug(calls: Calls, clean_logger: logging.Logger) -> None:
    result = runner.invoke(app, ["open", "web", "--debug", "--log-level", "error"])

    assert result.exit_code == 0
    assert clean_logger.level == logging.ERROR


def test_log_file_is_written_for_serve(
    calls: Calls, clean_logger: logging.Logger, tmp_path: Path
) -> None:
    log = tmp_path / "out.log"

    result = runner.invoke(app, ["serve", "web", "--log-file", str(log)])

    assert result.exit_code == 0
    assert clean_logger.level == logging.DEBUG  # the file is the full log
    assert log.exists()


def test_no_logging_flags_leave_logging_alone(calls: Calls, clean_logger: logging.Logger) -> None:
    result = runner.invoke(app, ["open", "web"])

    assert result.exit_code == 0
    assert clean_logger.handlers == []


def test_an_unwritable_log_file_is_a_short_error(calls: Calls, tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")

    result = runner.invoke(app, ["open", "web", "--log-file", str(blocker / "cornea.log")])

    assert result.exit_code == 1
    assert "could not open the log file" in result.output


# ----- debug mode ------------------------------------------------------------------------------


def _ignoring_pytest(logger: logging.Logger | None) -> bool:
    """Like Logger.hasHandlers, but pytest's own capture handlers do not count."""
    while logger is not None:
        if any(not type(h).__module__.startswith("_pytest") for h in logger.handlers):
            return True
        logger = logger.parent if logger.propagate else None
    return False


@pytest.fixture
def nothing_configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """No program-chosen handler on the cornea or the root logger, and a fresh folder."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Logs, "_has_handlers", _ignoring_pytest)
    return tmp_path


def test_debug_mode_logs_to_the_local_app_data_folder(nothing_configured: Path) -> None:
    written = Logs.enable_debug()

    logging.getLogger("cornea.test").debug("a detail")

    assert written == nothing_configured / "appdata" / "Cornea" / "logs" / "cornea.log"
    assert Logs.default_log_file() == written
    text = written.read_text(encoding="utf-8")
    assert "a detail" in text
    assert "Debug mode: writing the log to" in text


def test_debug_mode_leaves_existing_logging_alone(nothing_configured: Path) -> None:
    configure_logging("error")

    assert Logs.enable_debug() is None
    assert not (nothing_configured / "appdata").exists()


def test_debug_mode_respects_the_programs_own_logging(nothing_configured: Path) -> None:
    root = logging.getLogger()
    root.addHandler(logging.NullHandler())
    try:
        assert Logs.enable_debug() is None
    finally:
        root.handlers = [h for h in root.handlers if not isinstance(h, logging.NullHandler)]
    assert not (nothing_configured / "appdata").exists()


def test_a_debug_window_turns_on_debug_logging(
    nothing_configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    monkeypatch.setattr(window_module, "_registry_version", lambda: "1")
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace())
    monkeypatch.setattr(
        shell_module,
        "create_native_window",
        lambda *args: (None, SimpleNamespace(activate=lambda: None)),
    )
    monkeypatch.setattr(shell_module, "show_window", lambda *args: None)

    Shell(Static(tmp_path), window=Window(debug=True)).run()

    assert "Serving on http://127.0.0.1:" in (
        tmp_path / "appdata" / "Cornea" / "logs" / "cornea.log"
    ).read_text(encoding="utf-8")


def test_a_window_without_debug_writes_no_log(
    nothing_configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    monkeypatch.setattr(window_module, "_registry_version", lambda: "1")
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace())
    monkeypatch.setattr(
        shell_module,
        "create_native_window",
        lambda *args: (None, SimpleNamespace(activate=lambda: None)),
    )
    monkeypatch.setattr(shell_module, "show_window", lambda *args: None)

    Shell(Static(tmp_path), window=Window()).run()

    assert not (tmp_path / "appdata").exists()


def test_the_cli_debug_flag_writes_the_default_log_file(
    calls: Calls, nothing_configured: Path
) -> None:
    result = runner.invoke(app, ["open", "web", "--debug"])

    assert result.exit_code == 0
    assert (nothing_configured / "appdata" / "Cornea" / "logs" / "cornea.log").exists()


def test_debug_mode_logs_to_the_screen_when_the_file_cannot_be_written(
    nothing_configured: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = nothing_configured / "appdata"
    blocker.write_text("not a folder", encoding="utf-8")  # LOCALAPPDATA\Cornea cannot be made

    assert Logs.enable_debug() is None
    logging.getLogger("cornea.test").debug("still logged")

    err = capsys.readouterr().err
    assert "cannot write" in err
    assert "still logged" in err


def test_a_wrong_host_is_a_warning_without_turning_logging_on(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    (tmp_path / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    caplog.set_level(logging.WARNING, logger="cornea")
    with Shell(Static(tmp_path), window=None) as shell:
        connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
        connection.request("GET", "/", headers={"Host": "evil.example"})
        assert connection.getresponse().status == 403
        connection.close()

    assert "Refused GET /: unexpected Host header" in caplog.text


def test_a_missing_session_is_only_a_debug_message(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    (tmp_path / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    caplog.set_level(logging.WARNING, logger="cornea")
    with Shell(Static(tmp_path), window=None) as shell:
        connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
        connection.request("GET", "/")
        assert connection.getresponse().status == 401
        connection.close()

    assert "Refused" not in caplog.text


def test_the_debug_log_starts_with_the_environment(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    (tmp_path / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    caplog.set_level(logging.DEBUG, logger="cornea")

    Shell(Static(tmp_path), window=None).run(on_ready=lambda shell: shell.stop())

    assert "python: " in caplog.text
    assert "Window: None" in caplog.text
    assert "Security: Security(" in caplog.text
