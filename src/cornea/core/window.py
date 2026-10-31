"""The native window: pywebview on the WebView2 engine (Windows only)."""

import importlib
import logging
import sys
import threading
from collections.abc import Callable, Sequence
from types import ModuleType
from typing import Any, Literal, Protocol

from cornea.core.config import Window

logger = logging.getLogger(__name__)

WEBVIEW2_DOWNLOAD = "https://developer.microsoft.com/microsoft-edge/webview2/"
_WEBVIEW2_CLIENT = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
CLOSE_DELAY = 0.05
"""Seconds between answering a close request and closing, so the answer can be sent."""


DialogKind = Literal["folder", "open", "save"]


class Unavailable(Exception):
    """Raised for something that needs a real window when there is none."""


class WindowController(Protocol):
    """What the window routes call. The native window and the headless stand-in both fit."""

    @property
    def headless(self) -> bool:
        """Whether this is a stand-in with no real window behind it."""
        ...

    def minimize(self) -> None: ...
    def maximize(self) -> None: ...
    def restore(self) -> None: ...
    def close(self) -> None: ...
    def set_title(self, title: str) -> None: ...
    def state(self) -> dict[str, Any]: ...
    def dialog(
        self,
        kind: DialogKind,
        *,
        directory: str | None = None,
        filename: str | None = None,
        file_types: Sequence[str] = (),
        multiple: bool = False,
    ) -> list[str] | None: ...


# ----- the environment ------------------------------------------------------------------------


def require_windows() -> None:
    """Raise a clear error on any platform other than Windows."""
    if sys.platform != "win32":
        raise RuntimeError("Cornea windows only work on Windows for now.")


def _registry_version() -> str | None:
    """The installed WebView2 runtime version, or ``None``."""
    import winreg

    for hive, view in (
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
        (winreg.HKEY_CURRENT_USER, 0),
    ):
        try:
            with winreg.OpenKey(hive, _WEBVIEW2_CLIENT, 0, winreg.KEY_READ | view) as key:
                version = str(winreg.QueryValueEx(key, "pv")[0])
        except OSError:
            continue
        if version and version != "0.0.0.0":  # noqa: S104 - a version number, not an address
            return version
    return None


def require_webview2() -> str:
    """Return the WebView2 runtime version, or raise with where to get it."""
    version = _registry_version()
    if version is None:
        raise RuntimeError(
            "The Microsoft Edge WebView2 runtime is not installed. "
            f"Install it from {WEBVIEW2_DOWNLOAD} and run again."
        )
    return version


def load_webview() -> ModuleType:
    """Import pywebview, which comes with cornea-shell on Windows."""
    try:
        return importlib.import_module("webview")
    except ImportError as exc:
        raise RuntimeError(
            "pywebview is not installed. It comes with cornea-shell on Windows; "
            "reinstall with: pip install --force-reinstall cornea-shell"
        ) from exc


# ----- controlling a window -------------------------------------------------------------------


class NativeWindow:
    """Controls one pywebview window and remembers whether it is maximized or minimized."""

    def __init__(self, window: Any, settings: Window, webview: ModuleType | None = None) -> None:
        self._window = window
        self._webview = webview
        self._title = settings.title
        self._maximized = False
        self._minimized = False
        self._closed = False
        window.events.maximized += self._on_maximized
        window.events.minimized += self._on_minimized
        window.events.restored += self._on_restored
        window.events.closed += self._on_closed

    def _on_maximized(self) -> None:
        self._maximized, self._minimized = True, False

    def _on_minimized(self) -> None:
        self._minimized = True

    def _on_restored(self) -> None:
        self._maximized, self._minimized = False, False

    def _on_closed(self) -> None:
        self._closed = True

    @property
    def headless(self) -> bool:
        return False

    def minimize(self) -> None:
        self._window.minimize()

    def maximize(self) -> None:
        self._window.maximize()

    def restore(self) -> None:
        self._window.restore()

    def close(self) -> None:
        """Close the window shortly after, so the request that asked for it is answered first."""
        threading.Timer(CLOSE_DELAY, self._window.destroy).start()

    def set_title(self, title: str) -> None:
        self._title = title
        self._window.set_title(title)

    def state(self) -> dict[str, Any]:
        return {
            "title": self._title,
            "maximized": self._maximized,
            "minimized": self._minimized,
            "closed": self._closed,
        }

    def dialog(
        self,
        kind: DialogKind,
        *,
        directory: str | None = None,
        filename: str | None = None,
        file_types: Sequence[str] = (),
        multiple: bool = False,
    ) -> list[str] | None:
        """Show a native file or folder dialog. ``None`` means it was cancelled."""
        if self._webview is None:
            raise Unavailable("There is no window to show a dialog in.")
        kinds = self._webview.FileDialog
        chosen = self._window.create_file_dialog(
            {"folder": kinds.FOLDER, "open": kinds.OPEN, "save": kinds.SAVE}[kind],
            directory=directory or "",
            allow_multiple=multiple,
            save_filename=filename or "",
            file_types=tuple(file_types),
        )
        return [str(path) for path in chosen] if chosen else None


class SimulatedWindow:
    """A window that only exists in memory, for running without one.

    The page can still call the window routes, which makes a frameless UI testable in a normal
    browser. Closing only marks the window closed; the server keeps serving.

    Example:
        >>> window = SimulatedWindow("Demo")
        >>> window.maximize()
        >>> window.state()["maximized"]
        True
    """

    def __init__(self, title: str) -> None:
        self._title = title
        self._maximized = False
        self._minimized = False
        self._closed = False

    @property
    def headless(self) -> bool:
        return True

    def minimize(self) -> None:
        self._minimized = True

    def maximize(self) -> None:
        self._maximized, self._minimized = True, False

    def restore(self) -> None:
        self._maximized, self._minimized = False, False

    def close(self) -> None:
        self._closed = True

    def set_title(self, title: str) -> None:
        self._title = title

    def state(self) -> dict[str, Any]:
        return {
            "title": self._title,
            "maximized": self._maximized,
            "minimized": self._minimized,
            "closed": self._closed,
        }

    def dialog(
        self,
        kind: DialogKind,
        *,
        directory: str | None = None,
        filename: str | None = None,
        file_types: Sequence[str] = (),
        multiple: bool = False,
    ) -> list[str] | None:
        raise Unavailable("Dialogs need a window; this is running without one.")


# ----- opening a window -----------------------------------------------------------------------


def _invoke(native: Any, function: Callable[[], None]) -> None:
    """Run ``function`` on the window's own UI thread, which WebView2 settings require."""
    from System import Func, Type  # type: ignore[import-not-found]

    native.Invoke(Func[Type](function))


def apply_webview_settings(window: Any, settings: Window) -> None:
    """Set each WebView2 option to exactly what the settings ask for.

    pywebview ties the context menu, developer tools, shortcut keys and status bar to one debug
    switch. The window starts in debug mode when any of them is wanted, and this narrows it again.
    """

    def apply() -> None:
        options = window.native.webview.CoreWebView2.Settings
        options.AreDefaultContextMenusEnabled = settings.context_menu_enabled
        options.AreDevToolsEnabled = settings.devtools_enabled
        options.AreBrowserAcceleratorKeysEnabled = settings.devtools_enabled
        options.IsStatusBarEnabled = settings.debug

    _invoke(window.native, apply)


def create_native_window(
    webview: ModuleType, url: str, settings: Window, on_error: Callable[[BaseException], None]
) -> tuple[Any, NativeWindow]:
    """Create (not yet show) the window and its controller."""
    width, height = settings.size
    x, y = settings.position if settings.position is not None else (None, None)
    window = webview.create_window(
        settings.title,
        url,
        width=width,
        height=height,
        x=x,
        y=y,
        min_size=settings.min_size,
        resizable=settings.resizable,
        frameless=settings.frameless,
        on_top=settings.on_top,
        # A frameless window is dragged by elements with the `pywebview-drag-region` class,
        # not by any point of the page.
        easy_drag=False,
    )

    def narrow_settings() -> None:
        try:
            apply_webview_settings(window, settings)
        except BaseException as exc:
            # Failing open would leave tools on that were not asked for.
            logger.exception("Could not apply the window settings; closing the window")
            on_error(exc)
            window.destroy()

    window.events.loaded += narrow_settings
    return window, NativeWindow(window, settings, webview)


def show_window(webview: ModuleType, settings: Window) -> None:
    """Run the window's event loop. It must be called on the main thread and blocks until closed."""
    # The developer tools are available when wanted but never pop up by themselves.
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    webview.start(
        gui="edgechromium",
        debug=settings.context_menu_enabled or settings.devtools_enabled,
        private_mode=True,
    )
