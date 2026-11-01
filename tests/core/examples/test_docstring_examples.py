import doctest
import logging
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from cornea.core import config, shell
from cornea.core.app import app as app_module
from cornea.core.bridge import bridge
from cornea.core.sources import sources
from cornea.core.window import window as window_module


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


@pytest.mark.parametrize(
    "module",
    [app_module, bridge, config, shell, sources, window_module],
    ids=lambda module: module.__name__,
)
def test_docstring_examples_run(module: ModuleType) -> None:
    result = doctest.testmod(module)

    assert result.attempted > 0
    assert result.failed == 0
