"""Holding a window open while the app is busy."""

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


class CloseGuard:
    """Decides whether closing the window should be held back.

    The app can hold it in two ways: Python functions that return ``True`` while something would
    be lost (``@shell.close_guard``), and the page itself, which switches it on and off with
    ``POST /api/window/close-guard``. A function that fails never holds the window: an app with a
    bug can still be closed.
    """

    def __init__(self) -> None:
        self._functions: list[Callable[[], bool]] = []
        self.page_holds = False
        """Set by the page through the window routes."""

    def add(self, function: Callable[[], bool]) -> None:
        """Hold the window whenever ``function()`` returns true."""
        self._functions.append(function)

    def holds(self) -> bool:
        """Whether closing should be held back right now."""
        if self.page_holds:
            return True
        for function in self._functions:
            try:
                if function():
                    return True
            except Exception:
                logger.exception("A close guard failed; the window is allowed to close")
        return False
