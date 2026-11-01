"""Cornea Shell: host a web UI in a native window backed by a secured local server."""

__version__ = "0.1.0"

from cornea.core.app import AppFactory
from cornea.core.config import DEV_CSP, App, Bridge, Security, Server, Window
from cornea.core.logs import LOG_LEVELS, LogLevel, Logs
from cornea.core.shell import Shell, Timings, ready_line, run
from cornea.core.sources.sources import Asgi, Process, Static, Url, WebSource, Wsgi

create_app = AppFactory.create
configure_logging = Logs.configure

__all__ = [
    "DEV_CSP",
    "LOG_LEVELS",
    "App",
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
    "ready_line",
    "run",
]
