"""Cornea Shell: host a web UI in a native window backed by a secured local server.

``import cornea`` stays quick: the server (FastAPI, uvicorn) loads the first time you use
``Shell``, ``run``, ``create_app`` or ``AppFactory``. Call :func:`cornea.preload` early to load it
in the background while your own start-up code runs.
"""

__version__ = "0.1.0"

from typing import TYPE_CHECKING, Any

from cornea.core.config import DEV_CSP, App, Bridge, Security, Server, Window
from cornea.core.logs import LOG_LEVELS, LogLevel, Logs
from cornea.core.preload import preload
from cornea.core.sources.sources import Asgi, Process, Static, Url, WebSource, Wsgi

if TYPE_CHECKING:
    from cornea.core.app.app import AppFactory
    from cornea.core.shell import Shell, Timings, ready_line, run

    create_app = AppFactory.create

configure_logging = Logs.configure

# Names that need the server libraries, and the module that has each of them.
_LAZY = {
    "AppFactory": "cornea.core.app.app",
    "Shell": "cornea.core.shell",
    "Timings": "cornea.core.shell",
    "ready_line": "cornea.core.shell",
    "run": "cornea.core.shell",
}

__all__ = [
    "DEV_CSP",
    "LOG_LEVELS",
    "App",
    "AppFactory",
    "Asgi",
    "Bridge",
    "LogLevel",
    "Process",
    "Security",
    "Server",
    "Shell",
    "Static",
    "Timings",
    "Url",
    "WebSource",
    "Window",
    "Wsgi",
    "__version__",
    "configure_logging",
    "create_app",
    "preload",
    "ready_line",
    "run",
]


def __getattr__(name: str) -> Any:
    """Load the server on first use of a name that needs it (PEP 562)."""
    import importlib

    if name == "create_app":
        value = importlib.import_module("cornea.core.app.app").AppFactory.create
    elif name in _LAZY:
        value = getattr(importlib.import_module(_LAZY[name]), name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value  # later lookups skip this function
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
