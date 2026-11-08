"""Load the server libraries in the background, while the caller does other work.

FastAPI, Starlette and uvicorn take a few hundred milliseconds to import, so ``import cornea``
leaves them out. :func:`preload` starts importing them on a daemon thread, so that time overlaps
with work the caller does anyway, such as reading settings or checking the machine. Anything that
needs them afterwards waits for the thread through Python's own import lock, so calling
:func:`preload` is never required, only faster.
"""

import importlib
import logging
import threading

logger = logging.getLogger(__name__)

MODULES = ("fastapi", "uvicorn", "starlette.staticfiles", "cornea.core.app.app")
"""What the server needs, slowest first. The last one pulls in the routes."""

_lock = threading.Lock()
_thread: threading.Thread | None = None


def _load() -> None:
    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception:
            # Not fatal here: the code that needs the module imports it again and raises there.
            logger.debug("Could not preload %s", name, exc_info=True)
            return


def preload() -> threading.Thread:
    """Start importing the server libraries in the background. Safe to call more than once.

    Returns the thread, so a caller (or a test) can :meth:`~threading.Thread.join` it.

    Example:
        >>> preload().join()
        >>> import sys
        >>> "fastapi" in sys.modules
        True
    """
    global _thread
    with _lock:
        if _thread is None:
            _thread = threading.Thread(target=_load, name="cornea-preload", daemon=True)
            _thread.start()
        return _thread
