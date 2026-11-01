"""What Cornea runs on, for the top of a debug log."""

import importlib.metadata
import platform
import sys

from cornea.core.appdata import logs_dir


def environment_details() -> dict[str, str]:
    """The versions and places that matter when something goes wrong."""
    from cornea import __version__

    details = {
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    if sys.platform == "win32":
        from cornea.core.window import _registry_version

        details["webview2"] = _registry_version() or "not installed"
        try:
            details["pywebview"] = importlib.metadata.version("pywebview")
        except importlib.metadata.PackageNotFoundError:
            details["pywebview"] = "not installed"
    details["logs"] = str(logs_dir())
    return details
