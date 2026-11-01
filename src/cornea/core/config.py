"""Typed, frozen settings. Everything is a parameter; nothing is read from the environment."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)

DEV_CSP = DEFAULT_CSP.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'").replace(
    "style-src 'self'", "style-src 'self' 'unsafe-inline'"
)
"""The default policy plus inline scripts and styles, which development servers such as Vite
inject for hot reload. Nothing else is loosened. It is for development only and is never the
default. Use it with ``Security(csp=DEV_CSP)`` or ``--csp-profile dev``."""

ICON_TYPES = frozenset({".ico", ".png", ".bmp", ".gif", ".jpg", ".jpeg"})

Size = tuple[int, int]


def _check_size(name: str, size: Size) -> None:
    width, height = size
    if width <= 0 or height <= 0:
        raise ValueError(f"{name} must be positive, got {size}")


@dataclass(frozen=True, slots=True)
class Server:
    """Where the local server listens. Port 0 picks a free port.

    Example:
        >>> Server(port=8080)
        Server(host='127.0.0.1', port=8080)
    """

    host: str = "127.0.0.1"
    """Address to bind. Keep the loopback default unless the server must be reachable elsewhere."""
    port: int = 0
    """Port to bind. ``0`` picks a free port."""

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("host must not be empty")
        if not 0 <= self.port <= 65535:
            raise ValueError(f"port must be between 0 and 65535, got {self.port}")


@dataclass(frozen=True, slots=True)
class Security:
    """Local server protections. The defaults are the strict ones.

    Example:
        >>> Security(allowed_hosts=("App.Local",)).allowed_hosts
        ('app.local',)
        >>> Security(csp="default-src 'self'; style-src 'self' 'unsafe-inline'").csp
        "default-src 'self'; style-src 'self' 'unsafe-inline'"
    """

    allowed_hosts: tuple[str, ...] = ()
    """Extra ``Host`` values to accept. The bound ``127.0.0.1:<port>`` is always allowed."""
    csp: str = DEFAULT_CSP
    """``Content-Security-Policy`` value. Relax it explicitly, for example ``style-src``."""
    api_prefix: str = "/api"
    """Path prefix the host app's routers are mounted under."""
    token_ttl: float = 60.0
    """Seconds the one-time bootstrap token stays valid."""
    cookie_samesite: Literal["strict", "lax"] = "strict"
    """``SameSite`` attribute of the session cookie."""
    public_paths: tuple[str, ...] = ("/health",)
    """Paths reachable without a session. An entry ending in ``/`` matches everything below it."""
    require_origin: bool = True
    """Reject POST, PUT, PATCH and DELETE requests that send no ``Origin`` header."""

    def __post_init__(self) -> None:
        hosts = tuple(host.strip().lower() for host in self.allowed_hosts)
        if not all(hosts):
            raise ValueError("allowed_hosts must not contain empty values")
        object.__setattr__(self, "allowed_hosts", hosts)
        if not self.csp.strip():
            raise ValueError("csp must not be empty")
        if not self.api_prefix.startswith("/") or self.api_prefix.endswith("/"):
            raise ValueError(
                f"api_prefix must start with '/' and not end with '/', got {self.api_prefix!r}"
            )
        if self.token_ttl <= 0:
            raise ValueError(f"token_ttl must be positive, got {self.token_ttl}")
        if not all(path.startswith("/") for path in self.public_paths):
            raise ValueError(f"public_paths must start with '/', got {self.public_paths!r}")


APP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True, slots=True)
class App:
    """Who the app is, for the things that must tell one app from another.

    The id names the app's data folder, the Windows taskbar identity (so its icon is not grouped
    under ``python.exe``) and the single-instance lock. Several copies run independently unless
    ``single_instance`` is on.

    Example:
        >>> App(id="com.example.notes", remember_window=True).remember_window
        True
    """

    id: str | None = None
    """A short name such as ``com.example.notes``: letters, digits, dots, dashes, underscores."""
    single_instance: bool = False
    """Allow one copy at a time: starting a second one brings the first window to the front."""
    remember_window: bool = False
    """Reopen the window where it was and at the size it had."""

    def __post_init__(self) -> None:
        if self.id is not None and not APP_ID.match(self.id):
            raise ValueError(
                f"id may use letters, digits, '.', '-' and '_' (up to 128), got {self.id!r}"
            )
        if (self.single_instance or self.remember_window) and self.id is None:
            raise ValueError("single_instance and remember_window need an id")


@dataclass(frozen=True, slots=True)
class Bridge:
    """Which built-in native actions the page may call. All of them are on by default.

    Example:
        >>> Bridge(disabled=("open_external",)).disabled
        ('open_external',)
    """

    disabled: tuple[str, ...] = ()
    """Built-in actions to switch off. A disabled action answers like an unknown one."""


@dataclass(frozen=True, slots=True)
class Window:
    """Native window options. The context menu and developer tools are off unless enabled.

    Example:
        >>> Window(title="My App", frameless=True).title
        'My App'
        >>> Window().devtools_enabled
        False
        >>> Window(debug=True).devtools_enabled
        True
    """

    title: str = "Cornea Shell"
    """Window title."""
    size: Size = (1024, 768)
    """Initial width and height in pixels."""
    min_size: Size = (400, 300)
    """Smallest width and height the user can resize to."""
    position: Size | None = None
    """Top-left corner on screen; ``None`` lets the system place the window."""
    frameless: bool = False
    """Hide the native title bar; the web UI draws its own."""
    resizable: bool = True
    """Let the user resize the window."""
    on_top: bool = False
    """Keep the window above other windows."""
    context_menu: bool = False
    """Enable the right-click menu. Off by default."""
    devtools: bool = False
    """Enable the developer tools. Off by default."""
    debug: bool = False
    """Debug mode turns on the context menu and developer tools."""
    icon: Path | str | None = None
    """Icon for the window and its taskbar button: an ``.ico`` file or an image
    (``.png``, ``.bmp``, ``.gif``, ``.jpg``). A relative path is relative to the current folder."""
    js_api: bool = False
    """Give the page ``window.pywebview.api``: the window controls and the native actions.

    It lets a frameless window show an address that Cornea does not serve. Every page that loads
    in the window gets these powers, so use it only for pages you trust."""

    def __post_init__(self) -> None:
        _check_size("size", self.size)
        _check_size("min_size", self.min_size)
        if self.icon is not None and Path(self.icon).suffix.lower() not in ICON_TYPES:
            raise ValueError(
                f"icon must be one of {', '.join(sorted(ICON_TYPES))}, got {str(self.icon)!r}"
            )

    @property
    def context_menu_enabled(self) -> bool:
        """Whether the right-click menu is available."""
        return self.context_menu or self.debug

    @property
    def devtools_enabled(self) -> bool:
        """Whether the developer tools can be opened."""
        return self.devtools or self.debug
