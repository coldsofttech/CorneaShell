"""Cornea Shell: host a web UI in a native window backed by a secured local server."""

__version__ = "0.1.0"

from cornea.core.config import Security, Server, Window

__all__ = ["Security", "Server", "Window", "__version__"]
