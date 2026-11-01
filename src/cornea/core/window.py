"""The native window: pywebview on the WebView2 engine (Windows only)."""

import contextlib
import importlib
import json
import logging
import re
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Literal, Protocol

from cornea.core.appdata import data_dir
from cornea.core.close_guard import CloseGuard
from cornea.core.config import App, Window
from cornea.core.window_memory import Remembered, WindowMemory, fit_to_screens

if TYPE_CHECKING:
    from cornea.core.bridge import ActionRegistry
    from cornea.core.notifications import Notifier

logger = logging.getLogger(__name__)

WEBVIEW2_DOWNLOAD = "https://developer.microsoft.com/microsoft-edge/webview2/"
_WEBVIEW2_CLIENT = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
OFF_SCREEN = -30000
"""Windows reports minimized windows near this coordinate; never a real place."""
CLOSE_DELAY = 0.05
"""Seconds between answering a close request and closing, so the answer can be sent."""


DialogKind = Literal["folder", "open", "save"]


EVENT_PREFIX = "cornea:"
"""Every event sent to the page is a DOM event on ``window`` named with this prefix."""
EVENT_NAME = re.compile(r"^[a-z][a-z0-9_.-]*$")


def check_event_name(event: str) -> None:
    """Event names are lowercase words, like ``export-done`` (sent as ``cornea:export-done``)."""
    if not EVENT_NAME.match(event):
        raise ValueError(f"event names look like 'export-done', got {event!r}")


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
    def close(self, force: bool = False) -> bool:
        """Close the window, unless the app holds it open and ``force`` is not given.

        Returns whether the window is closing.
        """
        ...

    def notify(self, event: str, detail: object = None) -> None:
        """Tell the page something happened: a ``cornea:<event>`` event on its ``window``."""
        ...

    def show_notification(
        self, title: str, message: str, notification_id: str | None = None
    ) -> None:
        """Show a Windows toast. Clicking it activates the window and tells the page."""
        ...

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

    def __init__(
        self,
        window: Any,
        settings: Window,
        webview: ModuleType | None = None,
        start: Remembered | None = None,
    ) -> None:
        self._window = window
        self._webview = webview
        self._frameless = settings.frameless
        self._title = settings.title
        self._maximized = bool(start and start.maximized)
        self._minimized = False
        self._closed = False
        # The window's place when it is neither maximized nor minimized: what gets remembered.
        if start is not None:
            self._x, self._y = start.x, start.y
            self._width, self._height = start.width, start.height
        else:
            self._x, self._y = settings.position if settings.position else (None, None)
            self._width, self._height = settings.size
        self.guard: CloseGuard | None = None
        """Decides whether closing is held back. Set by the shell."""
        self.notifier: Notifier | None = None
        """Shows toasts for this app. Set by the shell."""
        self._forced = False
        window.events.closing += self._on_closing
        window.events.maximized += self._on_maximized
        window.events.minimized += self._on_minimized
        window.events.restored += self._on_restored
        window.events.closed += self._on_closed
        window.events.moved += self._on_moved
        window.events.resized += self._on_resized

    def _on_moved(self, x: int, y: int) -> None:
        if not self._maximized and not self._minimized and x > OFF_SCREEN and y > OFF_SCREEN:
            self._x, self._y = x, y

    def _on_resized(self, width: int, height: int) -> None:
        if not self._maximized and not self._minimized and width > 0 and height > 0:
            self._width, self._height = width, height

    def remember(self) -> Remembered:
        """Where the window is, for reopening it there. A maximized one keeps its normal place."""
        if (self._x is None or self._y is None) and not self._maximized and not self._minimized:
            # Placed by the system and never moved: ask the window itself.
            with contextlib.suppress(Exception):
                self._x, self._y = int(self._window.x), int(self._window.y)
        return Remembered(self._width, self._height, self._x, self._y, self._maximized)

    def activate(self) -> None:
        """Bring the window to the front, restoring it first if it was minimized."""
        if self._minimized:
            self._window.restore()
        self._window.show()
        with contextlib.suppress(Exception):  # focusing is a courtesy; it must not raise
            bring_to_front(self._window)

    def _on_maximized(self) -> None:
        self._maximized, self._minimized = True, False

    def _on_minimized(self) -> None:
        self._minimized = True

    def _on_restored(self) -> None:
        self._maximized, self._minimized = False, False

    def _on_closed(self) -> None:
        self._closed = True

    def _on_closing(self) -> bool:
        """The window is being closed by any means (Alt+F4, the taskbar): hold it if asked to."""
        if self._forced or self.guard is None or not self.guard.holds():
            return True
        self.notify("close-blocked")
        return False

    def show_notification(
        self, title: str, message: str, notification_id: str | None = None
    ) -> None:
        if self.notifier is None:
            raise Unavailable("There is no window to show a notification from.")

        def clicked() -> None:
            self.activate()
            self.notify("notification-click", {"id": notification_id})

        self.notifier.show(title, message, clicked)

    def notify(self, event: str, detail: object = None) -> None:
        check_event_name(event)
        script = (
            f"window.dispatchEvent(new CustomEvent({json.dumps(EVENT_PREFIX + event)}, "
            f"{{detail: {json.dumps(detail)}}}))"
        )
        try:
            self._window.evaluate_js(script)
        except Exception:
            logger.debug("Could not send the %r event to the page", event, exc_info=True)

    @property
    def headless(self) -> bool:
        return False

    def minimize(self) -> None:
        self._window.minimize()

    def maximize(self) -> None:
        self._window.maximize()

    def restore(self) -> None:
        self._window.restore()

    def close(self, force: bool = False) -> bool:
        """Close the window shortly after, so the request that asked for it is answered first.

        If the app holds the window open the page is told with a ``cornea:close-blocked`` event
        and nothing closes, unless ``force`` is given.
        """
        if not force and self.guard is not None and self.guard.holds():
            self.notify("close-blocked")
            return False
        self._forced = True
        threading.Timer(CLOSE_DELAY, self._window.destroy).start()
        return True

    def set_title(self, title: str) -> None:
        self._title = title
        self._window.set_title(title)

    def state(self) -> dict[str, Any]:
        return {
            "title": self._title,
            "maximized": self._maximized,
            "minimized": self._minimized,
            "closed": self._closed,
            "frameless": self._frameless,
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

    def close(self, force: bool = False) -> bool:
        self._closed = True
        return True

    def notify(self, event: str, detail: object = None) -> None:
        check_event_name(event)  # there is no page to tell

    def show_notification(
        self, title: str, message: str, notification_id: str | None = None
    ) -> None:
        raise Unavailable("There is no window to show a notification from.")

    def set_title(self, title: str) -> None:
        self._title = title

    def state(self) -> dict[str, Any]:
        return {
            "title": self._title,
            "maximized": self._maximized,
            "minimized": self._minimized,
            "closed": self._closed,
            "frameless": False,
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


def bring_to_front(window: Any) -> None:
    """Raise the window above the others and give it the keyboard focus."""

    def raise_it() -> None:
        form = window.native
        form.TopMost = True
        form.TopMost = False
        form.Activate()

    _invoke(window.native, raise_it)


def set_app_user_model_id(app_id: str) -> None:
    """Tell Windows which app this is, so its icon is not grouped under python.exe."""
    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.WinDLL("shell32")
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
    shell32.SetCurrentProcessExplicitAppUserModelID(app_id)


def screen_rectangles(webview: ModuleType) -> list[tuple[int, int, int, int]]:
    """The screens as ``(x, y, width, height)``, or none if they cannot be read."""
    try:
        return [(s.x, s.y, s.width, s.height) for s in webview.screens()]
    except Exception:
        return []


def apply_icon(window: Any, path: Path) -> None:
    """Put the icon on the window and its taskbar button."""

    def set_icon() -> None:
        from System.Drawing import Bitmap, Icon  # type: ignore[import-not-found]

        if path.suffix.lower() == ".ico":
            window.native.Icon = Icon(str(path))
        else:
            window.native.Icon = Icon.FromHandle(Bitmap(str(path)).GetHicon())

    _invoke(window.native, set_icon)


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


def _install_drop(window: Any, controller: "NativeWindow") -> None:
    """Send the full paths of files dropped on the window to the page, once it has loaded."""
    installed = False

    def on_drop(event: dict[str, Any]) -> None:
        files = (event.get("dataTransfer") or {}).get("files") or []
        paths = [f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")]
        logger.debug("%d dropped file(s) sent to the page", len(paths))
        controller.notify("drop", {"paths": paths})

    def install() -> None:
        nonlocal installed
        if installed:
            return
        try:
            from webview.dom import DOMEventHandler

            events = window.dom.document.events
            events.dragover += DOMEventHandler(lambda _event: None, True, True)
            events.drop += DOMEventHandler(on_drop, True, True)
        except Exception:
            logger.warning("Dropping files on the window is not available", exc_info=True)
        else:
            installed = True

    window.events.loaded += install


def create_native_window(
    webview: ModuleType,
    url: str,
    settings: Window,
    on_error: Callable[[BaseException], None],
    app: App | None = None,
    on_event: Callable[[str], None] | None = None,
    actions: "ActionRegistry | None" = None,
) -> tuple[Any, NativeWindow]:
    """Create (not yet show) the window and its controller."""
    width, height = settings.size
    x, y = settings.position if settings.position is not None else (None, None)
    maximized = False
    memory: WindowMemory | None = None
    start: Remembered | None = None
    if app is not None and app.id is not None:
        set_app_user_model_id(app.id)
        if app.remember_window:
            memory = WindowMemory(data_dir(app.id) / "window.json")
            saved = memory.load()
            if saved is not None:
                start = fit_to_screens(saved, screen_rectangles(webview), settings.min_size)
                width, height, x, y = start.width, start.height, start.x, start.y
                maximized = start.maximized
    extra: dict[str, Any] = {}
    api: Any = None
    if settings.js_api:
        # Imported here: both modules import this one.
        from cornea.core.bridge import ActionRegistry
        from cornea.core.window_api import WindowApi

        api = WindowApi(actions or ActionRegistry())
        extra["js_api"] = api
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
        maximized=maximized,
        # A frameless window is dragged by elements with the `pywebview-drag-region` class,
        # not by any point of the page.
        easy_drag=False,
        **extra,
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
    if settings.icon is not None:
        icon_path = Path(settings.icon).resolve()
        icon_set = False

        def set_icon() -> None:
            nonlocal icon_set
            if icon_set:
                return
            try:
                apply_icon(window, icon_path)
            except Exception:
                logger.warning("Could not set the window icon from %s", icon_path, exc_info=True)
            else:
                icon_set = True

        # Early, so the icon is there as the window appears; tried again on load if that failed.
        window.events.shown += set_icon
        window.events.loaded += set_icon
    if on_event is not None:
        # Reported as it happens so start-up can be timed; only the first page load counts.
        window.events.shown += lambda: on_event("window_shown")
        window.events.loaded += lambda: on_event("page_loaded")
    controller = NativeWindow(window, settings, webview, start)
    if settings.drop_files:
        _install_drop(window, controller)
    if api is not None:
        api._controller = controller
    if memory is not None:
        remembered_window = memory

        def save_place() -> None:
            with contextlib.suppress(OSError):  # not remembering beats failing to close
                remembered_window.save(controller.remember())

        window.events.closing += save_place
    return window, controller


def show_window(webview: ModuleType, settings: Window) -> None:
    """Run the window's event loop. It must be called on the main thread and blocks until closed."""
    # The developer tools are available when wanted but never pop up by themselves.
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    webview.start(
        gui="edgechromium",
        debug=settings.context_menu_enabled or settings.devtools_enabled,
        private_mode=True,
    )
