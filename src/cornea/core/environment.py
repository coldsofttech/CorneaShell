"""What Cornea runs on, for the top of a debug log."""

import importlib.metadata
import platform
import sys

from cornea.core.app.appdata import AppData


class Environment:
    """A description of the machine and the Cornea install."""

    @staticmethod
    def details() -> dict[str, str]:
        """The versions and places that matter when something goes wrong."""
        from cornea import __version__

        details = {
            "version": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
        }
        if sys.platform == "win32":
            from cornea.core.window.window import _registry_version

            details["webview2"] = _registry_version() or "not installed"
            try:
                details["pywebview"] = importlib.metadata.version("pywebview")
            except importlib.metadata.PackageNotFoundError:
                details["pywebview"] = "not installed"
        details["logs"] = str(AppData.logs_dir())
        return details
