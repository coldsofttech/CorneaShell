"""The system colour theme: light or dark, and the accent colour.

Read from the current user's Windows settings (``Personalize`` and ``DWM`` registry keys), so the
page can match the rest of the system. Nothing here is written, and the page only ever gets two
plain values. On a system without these settings the answer is a light theme with no accent.
"""

import contextlib
import logging
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

POLL_SECONDS = 1.0
"""How often a window looks for a theme change. Windows has no cheap change event to wait on."""

_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_DWM = r"Software\Microsoft\Windows\DWM"

Mode = Literal["light", "dark"]


@dataclass(frozen=True)
class Theme:
    """The system theme: ``mode`` is ``light`` or ``dark``, ``accent`` is ``#rrggbb`` or None."""

    mode: Mode = "light"
    accent: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"mode": self.mode, "accent": self.accent}


def accent_from_abgr(value: int) -> str:
    """``#rrggbb`` from the ``0xAABBGGRR`` number Windows stores. The alpha is dropped."""
    return f"#{value & 0xFF:02x}{(value >> 8) & 0xFF:02x}{(value >> 16) & 0xFF:02x}"


def accent_from_argb(value: int) -> str:
    """``#rrggbb`` from a ``0xAARRGGBB`` number. The alpha is dropped."""
    return f"#{(value >> 16) & 0xFF:02x}{(value >> 8) & 0xFF:02x}{value & 0xFF:02x}"


def read_theme() -> Theme:
    """The current system theme. Never raises: what cannot be read falls back to the default."""
    if sys.platform != "win32":
        return Theme()
    import winreg

    def number(path: str, name: str) -> int | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                value, kind = winreg.QueryValueEx(key, name)
        except OSError:
            return None
        return value if kind == winreg.REG_DWORD and isinstance(value, int) else None

    light = number(_PERSONALIZE, "AppsUseLightTheme")
    mode: Mode = "dark" if light == 0 else "light"
    accent: str | None = None
    if (abgr := number(_DWM, "AccentColor")) is not None:
        accent = accent_from_abgr(abgr)
    elif (argb := number(_DWM, "ColorizationColor")) is not None:
        accent = accent_from_argb(argb)
    return Theme(mode, accent)


class ThemeWatcher:
    """Calls ``on_change(theme)`` when the system theme changes, from a background thread."""

    def __init__(
        self,
        on_change: Callable[[Theme], None],
        read: Callable[[], Theme] = read_theme,
        interval: float = POLL_SECONDS,
    ) -> None:
        self._on_change = on_change
        self._read = read
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.current = read()

    def start(self) -> None:
        """Start watching. Starting twice does nothing."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="cornea-theme", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def check(self) -> bool:
        """Read the theme once and report a change. Returns whether it changed."""
        theme = self._read()
        if theme == self.current:
            return False
        self.current = theme
        with contextlib.suppress(Exception):
            self._on_change(theme)
        return True

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.check()
            except Exception:
                logger.debug("Could not read the system theme", exc_info=True)
