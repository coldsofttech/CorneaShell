import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

import cornea
from cli_support import Calls
from cornea.cli import doctor


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
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    recorded = Calls()
    monkeypatch.setattr("cornea.cli.commands.run_shell", recorded)
    return recorded


@pytest.fixture
def ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for the machine checks, so these tests do not depend on this machine."""
    monkeypatch.setattr(
        "cornea.cli.doctor.command.run_checks",
        lambda port: [doctor.Check("Cornea", "ok", cornea.__version__)],
    )
