"""Command line interface for Cornea Shell. A thin wrapper over the Python API."""

from cornea.cli.commands import app, run

# Importing a command module registers it on ``app``; the order is the order in the help.
from cornea.cli.doctor import command as _doctor_command  # noqa: F401
from cornea.cli.open import command as _open_command  # noqa: F401
from cornea.cli.serve import command as _serve_command  # noqa: F401

__all__ = ["app", "run"]
