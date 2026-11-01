import logging
import shlex
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cornea.cli import app
from cornea.cli.commands import EXAMPLES

runner = CliRunner()

CLI_EXAMPLES = [
    (command, example) for command, examples in EXAMPLES.items() for example in examples
]


@pytest.fixture(autouse=True)
def restore_cornea_logging(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """The log examples configure logging for real: keep their files and handlers to this test."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    logger = logging.getLogger("cornea")
    level, propagate = logger.level, logger.propagate
    yield
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(level)
    logger.propagate = propagate


@pytest.mark.parametrize(("command", "example"), CLI_EXAMPLES)
def test_cli_examples_run(command: str, example: str, monkeypatch: pytest.MonkeyPatch) -> None:
    program, *args = shlex.split(example)
    started: list[object] = []
    # `open` and `serve` would start a server or show a window; here they only have to parse.
    monkeypatch.setattr("cornea.cli.commands.run_shell", lambda *a, **k: started.append(a))

    result = runner.invoke(app, args)

    assert program == "cornea"
    assert result.exit_code == 0, result.output
    assert command in args or command == ""
    assert bool(started) == (command in {"open", "serve"})


def test_every_command_documents_examples() -> None:
    registered = {
        command.name or getattr(command.callback, "__name__", "")
        for command in app.registered_commands
    }

    assert registered <= set(EXAMPLES)
