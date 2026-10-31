"""Web sources: where the UI comes from. The app factory mounts whichever source is given."""

import importlib
import os
import re
import sys
from collections.abc import Awaitable, Callable, Iterable, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
AsgiApp = Callable[[Scope, Receive, Send], Awaitable[None]]
WsgiApp = Callable[..., Iterable[bytes]]

_IMPORT_STRING = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_][\w.]*$")


def _check_import_string(target: object) -> None:
    if isinstance(target, str):
        if not _IMPORT_STRING.match(target):
            raise ValueError(f"expected 'module:attribute', got {target!r}")
    elif not callable(target):
        raise TypeError(f"expected an import string or a callable, got {type(target).__name__}")


def _import_target(target: str, app_dir: Path | str | None) -> object:
    """Import ``module:attribute``. ``app_dir`` is added to ``sys.path`` first when given."""
    if app_dir is not None:
        directory = str(Path(app_dir).resolve())
        if directory not in sys.path:
            sys.path.insert(0, directory)
    module_name, _, attribute_path = target.partition(":")
    try:
        obj: object = importlib.import_module(module_name)
    except ImportError as exc:
        raise ImportError(f"cannot import module {module_name!r} from {target!r}: {exc}") from exc
    for name in attribute_path.split("."):
        try:
            obj = getattr(obj, name)
        except AttributeError as exc:
            raise ImportError(f"{module_name!r} has no attribute {attribute_path!r}") from exc
    return obj


@dataclass(frozen=True, slots=True)
class WebSource:
    """Base class for everything that can supply the web layer."""


@dataclass(frozen=True, slots=True)
class Static(WebSource):
    """A built bundle (React, Vite, Next export, plain HTML) served by the shell.

    Example:
        >>> Static("web/dist").directory.name
        'dist'
    """

    path: Path | str
    """Folder that contains ``index.html``."""

    @property
    def directory(self) -> Path:
        """The bundle folder as a :class:`~pathlib.Path`."""
        return Path(self.path)

    def resolve(self) -> Path:
        """Return the absolute bundle folder, or raise if it or its ``index.html`` is missing."""
        directory = self.directory.resolve()
        if not directory.is_dir():
            raise FileNotFoundError(f"web bundle folder not found: {directory}")
        if not (directory / "index.html").is_file():
            raise FileNotFoundError(f"index.html not found in web bundle: {directory}")
        return directory


@dataclass(frozen=True, slots=True)
class Url(WebSource):
    """An http or https server the window opens directly. The shell's security layer is skipped.

    Example:
        >>> Url("http://localhost:5173").mode
        'direct'
    """

    url: str
    """Address of the web UI, for example ``http://localhost:5173``."""
    mode: Literal["direct", "proxy"] = "direct"
    """``direct`` opens the address as is. ``proxy`` is planned for a later release."""

    def __post_init__(self) -> None:
        parts = urlsplit(self.url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError(f"url must be an absolute http or https address, got {self.url!r}")
        if self.mode == "proxy":
            raise ValueError("proxy mode is not available yet; use mode='direct'")
        if self.mode != "direct":
            raise ValueError(f"mode must be 'direct' or 'proxy', got {self.mode!r}")


@dataclass(frozen=True, slots=True)
class Asgi(WebSource):
    """An ASGI app (FastAPI, Django ASGI) mounted in-process on the shell's port.

    Example:
        >>> Asgi("myproject.asgi:application", app_dir=".").target
        'myproject.asgi:application'
    """

    target: str | AsgiApp
    """``module:attribute`` import string, or the app itself."""
    app_dir: Path | str | None = None
    """Folder added to ``sys.path`` before importing, for example the project root."""

    def __post_init__(self) -> None:
        _check_import_string(self.target)

    def load(self) -> AsgiApp:
        """Import the app if needed and return it."""
        app = (
            _import_target(self.target, self.app_dir)
            if isinstance(self.target, str)
            else self.target
        )
        if not callable(app):
            raise TypeError(f"{self.target!r} is not a callable ASGI app")
        return app


@dataclass(frozen=True, slots=True)
class Wsgi(WebSource):
    """A WSGI app (Flask, Django WSGI) adapted to ASGI and mounted in-process.

    Needs the ``wsgi`` extra: ``pip install cornea-shell[wsgi]``.

    Example:
        >>> Wsgi("myapp:app").target
        'myapp:app'
    """

    target: str | WsgiApp
    """``module:attribute`` import string, or the app itself."""
    app_dir: Path | str | None = None
    """Folder added to ``sys.path`` before importing, for example the project root."""

    def __post_init__(self) -> None:
        _check_import_string(self.target)

    def load(self) -> AsgiApp:
        """Import the app if needed and return it wrapped as an ASGI app."""
        try:
            from a2wsgi import WSGIMiddleware
        except ImportError as exc:
            raise ImportError(
                "WSGI apps need the 'wsgi' extra: pip install cornea-shell[wsgi]"
            ) from exc
        app = (
            _import_target(self.target, self.app_dir)
            if isinstance(self.target, str)
            else self.target
        )
        if not callable(app):
            raise TypeError(f"{self.target!r} is not a callable WSGI app")
        return WSGIMiddleware(app)  # type: ignore[return-value]


def coerce_source(value: "WebSource | str | os.PathLike[str]") -> WebSource:
    """Turn the shorthand forms into a source: http(s) strings are ``Url``, paths are ``Static``."""
    if isinstance(value, WebSource):
        return value
    if isinstance(value, str) and re.match(r"^https?://", value, re.IGNORECASE):
        return Url(value)
    if isinstance(value, str | os.PathLike):
        return Static(Path(value))
    raise TypeError(f"expected a web source, path or URL, got {type(value).__name__}")
