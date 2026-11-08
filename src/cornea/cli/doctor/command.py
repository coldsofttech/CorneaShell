"""``cornea doctor``: check that this machine is ready."""

from dataclasses import asdict
from typing import Annotated

import typer
from rich.table import Table
from rich.text import Text

from cornea.cli import output
from cornea.cli.commands import (
    JsonOption,
    app,
    epilog,
)
from cornea.cli.doctor.checks import run_checks


@app.command(epilog=epilog("doctor"))
def doctor(
    port: Annotated[
        int,
        typer.Option(
            help="Check that this port is free on 127.0.0.1 (0 checks that one can be opened)."
        ),
    ] = 0,
    json_output: JsonOption = False,
) -> None:
    """Check that this machine is ready to show a Cornea window."""
    checks = run_checks(port=port)
    failed = any(check.status == "fail" for check in checks)
    if json_output:
        output.console.print_json(data=[asdict(check) for check in checks])
    else:
        table = Table(title="cornea doctor")
        table.add_column("Check")
        table.add_column("Result")
        table.add_column("Details", overflow="fold")
        marks = {
            "ok": "[green]ok[/green]",
            "warn": "[yellow]warning[/yellow]",
            "fail": "[red]problem[/red]",
        }
        for check in checks:
            table.add_row(check.name, marks[check.status], Text(check.detail))
        output.console.print(table)
    if failed:
        raise typer.Exit(code=1)
