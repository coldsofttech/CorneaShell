import doctest
import shlex
from types import ModuleType

import pytest
from typer.testing import CliRunner

from cornea.cli import app
from cornea.cli.commands import EXAMPLES
from cornea.core import app as app_module
from cornea.core import config, shell, sources
from cornea.core import window as window_module

runner = CliRunner()

CLI_EXAMPLES = [
    (command, example) for command, examples in EXAMPLES.items() for example in examples
]


@pytest.mark.parametrize(
    "module",
    [app_module, config, shell, sources, window_module],
    ids=lambda module: module.__name__,
)
def test_docstring_examples_run(module: ModuleType) -> None:
    result = doctest.testmod(module)

    assert result.attempted > 0
    assert result.failed == 0


@pytest.mark.parametrize(("command", "example"), CLI_EXAMPLES)
def test_cli_examples_run(command: str, example: str) -> None:
    program, *args = shlex.split(example)

    result = runner.invoke(app, args)

    assert program == "cornea"
    assert result.exit_code == 0, result.output
    assert command in args or command == ""


def test_every_command_documents_examples() -> None:
    registered = {
        command.name or getattr(command.callback, "__name__", "")
        for command in app.registered_commands
    }

    assert registered <= set(EXAMPLES)
