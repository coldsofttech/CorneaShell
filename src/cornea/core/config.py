"""Typed, frozen settings. Everything is a parameter; nothing is read from the environment."""

from dataclasses import dataclass
from typing import Literal

DEFAULT_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)

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

    def __post_init__(self) -> None:
        _check_size("size", self.size)
        _check_size("min_size", self.min_size)

    @property
    def context_menu_enabled(self) -> bool:
        """Whether the right-click menu is available."""
        return self.context_menu or self.debug

    @property
    def devtools_enabled(self) -> bool:
        """Whether the developer tools can be opened."""
        return self.devtools or self.debug
