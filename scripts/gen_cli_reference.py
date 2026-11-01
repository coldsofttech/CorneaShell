#!/usr/bin/env python3
"""Refresh the generated parts of docs/cli-reference.md from the ``cornea`` command line.

The file is written by hand, except for the blocks between ``<!-- BEGIN GENERATED: NAME -->`` and
``<!-- END GENERATED -->``: the usage and options of each command (``typer open`` and so on), as
Typer builds them, and the example invocations registered in ``EXAMPLES`` (``examples``).

Usage: uv run python scripts/gen_cli_reference.py [file]
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
SECTION = re.compile(rf"^## `{COMMAND_NAME} (\w+)`\n", re.MULTILINE)
BLOCK = re.compile(
    r"(<!-- BEGIN GENERATED: ([\w ]+) -->\n)(.*?)(\n?<!-- END GENERATED -->)", re.DOTALL
)


def typer_sections() -> dict[str, str]:
    """Usage and options for each command, as Typer builds them, keyed by ``typer NAME``."""
    result = subprocess.run(
        [sys.executable, "-m", "typer", MODULE, "utils", "docs", "--name", COMMAND_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.exit(f"typer failed:\n{result.stderr.strip()}")
    text = EPILOG.sub("", result.stdout.replace("\r\n", "\n"))
    parts = SECTION.split(text)
    # parts is [top-level text, name, body, name, body, ...]
    return {
        f"typer {name}": body.strip("\n")
        for name, body in zip(parts[1::2], parts[2::2], strict=True)
    }


def examples_section() -> str:
    """Markdown for the example invocations that the CLI registers in ``EXAMPLES``."""
    lines = ["## Examples", "", "Every command, as registered in the CLI and run by the tests.", ""]
    for command, examples in EXAMPLES.items():
        title = f"{COMMAND_NAME} {command}".strip()
        lines += [f"### `{title}`", "", "```console", *(f"$ {example}" for example in examples)]
        lines += ["```", ""]
    return "\n".join(lines).rstrip("\n")


def refresh(text: str) -> str:
    """Return ``text`` with every generated block rewritten."""
    blocks = {**typer_sections(), "examples": examples_section()}
    found: set[str] = set()

    def fill(match: re.Match[str]) -> str:
        name = match.group(2)
        if name not in blocks:
            sys.exit(f"The file has a generated block '{name}', which the script does not know")
        found.add(name)
        return f"{match.group(1)}{blocks[name]}\n<!-- END GENERATED -->"

    text = BLOCK.sub(fill, text)
    if missing := set(blocks) - found:
        sys.exit(f"The file has no generated block for: {', '.join(sorted(missing))}")
    return text


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    text = target.read_text(encoding="utf-8").replace("\r\n", "\n")
    target.write_text(refresh(text), encoding="utf-8", newline="\n")
    print(f"CLI reference saved to: {target}")


if __name__ == "__main__":
    main()
