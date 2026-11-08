"""Where the UI comes from: bundles, apps, addresses, dev servers and processes."""

from typing import TYPE_CHECKING, Any

from cornea.core.sources.process import ProcessRunner
from cornea.core.sources.proxy import ProxyApp
from cornea.core.sources.sources import (
    Asgi,
    Process,
    Static,
    Url,
    WebSource,
    Wsgi,
    coerce_source,
)

if TYPE_CHECKING:
    from cornea.core.sources.static import BundleFiles

__all__ = [
    "Asgi",
    "BundleFiles",
    "Process",
    "ProcessRunner",
    "ProxyApp",
    "Static",
    "Url",
    "WebSource",
    "Wsgi",
    "coerce_source",
]


def __getattr__(name: str) -> Any:
    """Load ``BundleFiles`` on first use: it brings Starlette, which is slow to import."""
    if name == "BundleFiles":
        from cornea.core.sources.static import BundleFiles

        return BundleFiles
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
