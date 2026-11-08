import re
from typing import Any

from typer.main import get_command
from typer.testing import CliRunner

from cornea.cli import app

runner = CliRunner()


ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Calls:
    """Stands in for run(): remembers how the command called it."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def __call__(self, source: Any = None, **kwargs: Any) -> None:
        self.items.append({"source": source, **kwargs})

    @property
    def last(self) -> dict[str, Any]:
        return self.items[-1]


def invoke(*args: str) -> Any:
    return runner.invoke(app, list(args))


def option_names(command: str) -> set[str]:
    cli: Any = get_command(app)
    return {name for param in cli.commands[command].params for name in param.opts}
