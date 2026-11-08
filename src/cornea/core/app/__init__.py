"""The application factory and where an app keeps its files."""

from typing import TYPE_CHECKING, Any

from cornea.core.app.appdata import AppData

if TYPE_CHECKING:
    from cornea.core.app.app import AppFactory

__all__ = ["AppData", "AppFactory"]


def __getattr__(name: str) -> Any:
    """Load ``AppFactory`` on first use: it brings FastAPI, which is slow to import."""
    if name == "AppFactory":
        from cornea.core.app.app import AppFactory

        return AppFactory
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
