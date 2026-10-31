#!/usr/bin/env python3
"""Generate docs/cli-reference.md from the ``cornea`` command line interface.

Usage: uv run python scripts/gen_cli_reference.py [output]
CI regenerates the file and fails if it differs from the committed copy.
"""

import re
import subprocess
import sys
from pathlib import Path

from cornea.cli.commands import EXAMPLES

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "cli-reference.md"
MODULE = "cornea.cli"
COMMAND_NAME = "cornea"
# The help footer is rendered as raw markup by Typer; examples get their own section instead.
EPILOG = re.compile(r"\[bold\]Examples\[/bold\]\n(?:\n {2}\$ [^\n]+\n)+\n?")


def generate() -> str:
    """Return the Markdown reference that Typer builds for the CLI."""
    result = subprocess.run(
        [sys.executable, "-m", "typer", MODULE, "utils", "docs", "--name", COMMAND_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.exit(f"typer failed:\n{result.stderr.strip()}")
    text = EPILOG.sub("", result.stdout.replace("\r\n", "\n"))
    return text.rstrip("\n") + "\n" + examples_section()


def examples_section() -> str:
    """Markdown for the example invocations that the CLI registers in ``EXAMPLES``."""
    lines = ["", "## Examples", ""]
    for command, examples in EXAMPLES.items():
        title = f"{COMMAND_NAME} {command}".strip()
        lines += [f"### `{title}`", "", "```console", *(f"$ {example}" for example in examples)]
        lines += ["```", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.write_text(generate(), encoding="utf-8", newline="\n")
    print(f"CLI reference saved to: {output}")


if __name__ == "__main__":
    main()
