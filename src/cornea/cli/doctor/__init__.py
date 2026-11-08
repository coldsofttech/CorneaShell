"""The checks behind ``cornea doctor`` and the command itself."""

from cornea.cli.doctor.checks import Check, run_checks

__all__ = ["Check", "run_checks"]
