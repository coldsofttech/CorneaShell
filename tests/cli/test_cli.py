import re
from collections.abc import Callable

import pytest
from typer.testing import CliRunner

import cornea
from cornea.cli import app, output, run

runner = CliRunner()

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    """Remove color codes. Typer's help always colors output on GitHub Actions."""
    return ANSI.sub("", text)


def test_help_lists_commands_and_options() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for text in ("doctor", "open", "serve", "--version", "--verbose", "--quiet", "--no-color"):
        assert text in plain(result.output)


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert cornea.__version__ in result.output


def test_verbose_and_quiet_conflict(ready: None) -> None:
    result = runner.invoke(app, ["--verbose", "--quiet", "doctor"])

    assert result.exit_code == 2


def test_no_color_flag_is_accepted(ready: None) -> None:
    result = runner.invoke(app, ["--no-color", "doctor"])

    assert result.exit_code == 0
    assert cornea.__version__ in result.output


def test_quiet_flag_is_accepted(ready: None) -> None:
    result = runner.invoke(app, ["--quiet", "doctor"])

    assert result.exit_code == 0


def test_there_is_no_info_command() -> None:
    result = runner.invoke(app, ["info"])

    assert result.exit_code == 2


def _failing_app(*, verbose: bool) -> Callable[[], None]:
    """Stand in for the Typer app: set the output mode the real callback would, then fail."""

    def fail() -> None:
        output.configure(no_color=True, verbose=verbose)
        raise RuntimeError("boom")

    return fail


def test_unexpected_error_is_short_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("cornea.cli.commands.app", _failing_app(verbose=False))

    with pytest.raises(SystemExit) as exit_info:
        run()

    stderr = capsys.readouterr().err
    assert exit_info.value.code == 1
    assert "RuntimeError: boom" in stderr
    assert "--verbose" in stderr
    assert "Traceback" not in stderr


def test_unexpected_error_shows_traceback_with_verbose(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("cornea.cli.commands.app", _failing_app(verbose=True))

    with pytest.raises(SystemExit):
        run()

    assert "Traceback" in capsys.readouterr().err
