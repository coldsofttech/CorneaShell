"""Cornea Shell: host a web UI in a native window backed by a secured local server."""

__version__ = "0.1.0"

from cornea.core.config import Security, Server, Window
from cornea.core.sources import Asgi, Static, Url, WebSource, Wsgi

__all__ = [
    "Asgi",
    "Security",
    "Server",
    "Static",
    "Url",
    "WebSource",
    "Window",
    "Wsgi",
    "__version__",
]
