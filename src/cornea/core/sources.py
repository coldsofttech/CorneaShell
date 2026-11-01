"""Web sources: where the UI comes from. The app factory mounts whichever source is given."""

import importlib
import importlib.resources
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

    The bundle folder is found in this order: ``path``, then ``package_path`` inside the installed
    ``package``, then ``web/dist`` under the current folder (a source checkout). An explicit
    ``path`` is never replaced by a later place.

    Example:
        >>> Static("web/dist").directory.name
        'dist'
        >>> Static(package="myapp").package_path
        'web/dist'
    """

    path: Path | str | None = None
    """Folder that contains ``index.html``."""
    package: str | None = None
    """Import name of an installed package that ships the bundle."""
    package_path: str = "web/dist"
    """Folder inside ``package`` that contains ``index.html``."""
    spa: bool = True
    """Serve ``index.html`` for unknown paths without a file extension (client-side routing)."""
    hashed_prefixes: tuple[str, ...] = ("assets/",)
    """Folders of fingerprinted files, cached for a year. Everything else is revalidated."""

    def __post_init__(self) -> None:
        if not self.package_path.strip() or ".." in Path(self.package_path).parts:
            raise ValueError(
                f"package_path must be a folder inside the package, got {self.package_path!r}"
            )
        for prefix in self.hashed_prefixes:
            if not prefix.endswith("/") or prefix.startswith("/"):
                raise ValueError(f"hashed_prefixes must look like 'assets/', got {prefix!r}")

    @property
    def directory(self) -> Path | None:
        """The explicit bundle folder as a :class:`~pathlib.Path`, or ``None`` if not given."""
        return Path(self.path) if self.path is not None else None

    def resolve(self) -> Path:
        """Return the absolute bundle folder, or raise if it or its ``index.html`` is missing."""
        if self.directory is not None:
            directory = self.directory.resolve()
            if not directory.is_dir():
                raise FileNotFoundError(f"web bundle folder not found: {directory}")
            if not (directory / "index.html").is_file():
                raise FileNotFoundError(f"index.html not found in web bundle: {directory}")
            return directory
        tried: list[Path] = []
        for candidate in self._fallback_folders():
            tried.append(candidate)
            if (candidate / "index.html").is_file():
                return candidate.resolve()
        places = ", ".join(str(place) for place in tried) or "no place to look"
        raise FileNotFoundError(f"web bundle not found; looked in: {places}")

    def _fallback_folders(self) -> Iterable[Path]:
        if self.package is not None:
            try:
                root = importlib.resources.files(self.package)
            except ModuleNotFoundError:
                pass
            else:
                yield Path(str(root.joinpath(*Path(self.package_path).parts)))
        yield Path.cwd() / "web" / "dist"


@dataclass(frozen=True, slots=True)
class Url(WebSource):
    """A page from a server you already run, such as a dev server.

    In ``direct`` mode the window opens the address itself: the page is not served by Cornea, so it
    skips Cornea's security, needs the native window frame and cannot use the window controls.

    In ``proxy`` mode Cornea fetches the pages and serves them from its own address, so they get
    Cornea's security, the window controls and the frameless window, and hot reload keeps
    working. It needs the ``proxy`` extra: ``pip install "cornea-shell[proxy]"``.

    Example:
        >>> Url("http://localhost:5173").mode
        'direct'
        >>> Url("http://localhost:5173", mode="proxy").mode
        'proxy'
    """

    url: str
    """Address of the web UI, for example ``http://localhost:5173``."""
    mode: Literal["direct", "proxy"] = "direct"
    """``direct`` opens the address as it is. ``proxy`` serves it through Cornea."""

    def __post_init__(self) -> None:
        parts = urlsplit(self.url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError(f"url must be an absolute http or https address, got {self.url!r}")
        if self.mode not in {"direct", "proxy"}:
            raise ValueError(f"mode must be 'direct' or 'proxy', got {self.mode!r}")


@dataclass(frozen=True, slots=True)
class Process(WebSource):
    """A dev-server command that Cornea starts for you and stops with the window.

    Cornea runs ``command``, waits until something listens at ``url``, then shows that address
    exactly as :class:`Url` does, directly or through the proxy. When Cornea stops, or even if it
    crashes, the command and everything it started are stopped too.

    Example:
        >>> Process("npm run dev", url="http://localhost:5173").command
        'npm run dev'
    """

    command: str | tuple[str, ...]
    """The command. A string is run by the shell, so ``npm run dev`` works; a tuple is run as is."""
    url: str
    """Address the command serves on, for example ``http://localhost:5173``."""
    cwd: Path | str | None = None
    """Folder to run the command in."""
    mode: Literal["direct", "proxy"] = "direct"
    """As for :class:`Url`: ``direct`` opens the address, ``proxy`` serves it through Cornea."""
    timeout: float = 30.0
    """Seconds to wait for the address to answer before giving up."""

    def __post_init__(self) -> None:
        if not (self.command.strip() if isinstance(self.command, str) else self.command):
            raise ValueError("command must not be empty")
        Url(self.url, mode=self.mode)  # same checks as for an address
        if self.timeout <= 0:
            raise ValueError(f"timeout must be positive, got {self.timeout}")


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


def coerce_source(value: WebSource | str | os.PathLike[str]) -> WebSource:
    """Turn the shorthand forms into a source: http(s) strings are ``Url``, paths are ``Static``."""
    if isinstance(value, WebSource):
        return value
    if isinstance(value, str) and re.match(r"^https?://", value, re.IGNORECASE):
        return Url(value)
    if isinstance(value, str | os.PathLike):
        return Static(Path(value))
    raise TypeError(f"expected a web source, path or URL, got {type(value).__name__}")
