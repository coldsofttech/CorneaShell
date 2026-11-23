"""The system tray (the Windows notification area): an icon that keeps the app reachable.

With ``Window(tray=True)`` closing the window hides it and the app keeps running. The icon shows
the window icon and the window title as its tooltip. Clicking it shows the window; its menu has
**Show**, any items the app added with ``@shell.tray_item("...")``, and **Quit**.

The icon is a plain ``Shell_NotifyIcon`` call made through ``ctypes``, so nothing extra is
installed. It lives on its own thread with a hidden window that receives the icon's messages.
:class:`Tray` holds the behaviour (the menu, what each click does) and :class:`Win32Backend` holds
every call into Windows, so the behaviour can be tried without Windows.
"""

import ctypes
import logging
import threading
from collections.abc import Callable, Iterator
from ctypes import wintypes
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

MAX_LABEL = 64
MAX_TOOLTIP = 127
"""The most the tooltip can hold (``NOTIFYICONDATAW.szTip`` is 128 characters with its end)."""
SHOW_ID = 1
QUIT_ID = 2
FIRST_ITEM_ID = 100
START_TIMEOUT = 5.0


class TrayBackend(Protocol):
    """What :class:`Tray` needs from the system."""

    def start(self, tooltip: str, icon: Path | None, on_event: Callable[[str], None]) -> None:
        """Show the icon. ``on_event`` hears ``"click"``, ``"menu"`` and ``"restart"``."""
        ...

    def set_tooltip(self, tooltip: str) -> None: ...

    def choose(self, entries: list[tuple[int, str]]) -> int | None:
        """Show the menu at the pointer. Returns the id of the chosen entry, or ``None``."""
        ...

    def stop(self) -> None:
        """Remove the icon. Safe to call more than once."""
        ...


class TrayItems:
    """The app's own menu entries, in the order they were added."""

    def __init__(self) -> None:
        self._items: list[tuple[str, Callable[[], None]]] = []

    def add(self, label: str, function: Callable[[], None]) -> None:
        """Add an entry.

        Raises:
            ValueError: If the label is empty, too long, or already used (``Show`` and ``Quit``
                are the shell's own).
        """
        if not isinstance(label, str) or not label.strip():
            raise ValueError("a tray item needs a label")
        if len(label) > MAX_LABEL:
            raise ValueError(f"a tray item label can have at most {MAX_LABEL} characters")
        if label.casefold() in {"show", "quit"} or any(label == known for known, _ in self._items):
            raise ValueError(f"the tray already has an item called {label!r}")
        self._items.append((label, function))

    def labels(self) -> list[str]:
        return [label for label, _ in self._items]

    def __iter__(self) -> Iterator[tuple[str, Callable[[], None]]]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


class Tray:
    """One tray icon and what it does."""

    def __init__(
        self,
        title: str,
        icon: Path | None,
        items: TrayItems,
        *,
        show: Callable[[], object],
        quit: Callable[[], object],
        backend: TrayBackend | None = None,
    ) -> None:
        self._tooltip = self.tooltip_for(title)
        self._icon = icon
        self._items = items
        self._show = show
        self._quit = quit
        self._backend = backend if backend is not None else Win32Backend()
        self._started = False

    @staticmethod
    def tooltip_for(title: str) -> str:
        """The window title, cut to fit the tooltip."""
        return title if len(title) <= MAX_TOOLTIP else title[: MAX_TOOLTIP - 1] + "…"

    def start(self) -> None:
        """Put the icon in the notification area."""
        if self._started:
            return
        self._backend.start(self._tooltip, self._icon, self._on_event)
        self._started = True

    def stop(self) -> None:
        """Take the icon away. Safe to call more than once."""
        if self._started:
            self._started = False
            self._backend.stop()

    def set_title(self, title: str) -> None:
        """Keep the tooltip in step with the window title."""
        self._tooltip = self.tooltip_for(title)
        if self._started:
            self._backend.set_tooltip(self._tooltip)

    def entries(self) -> list[tuple[int, str]]:
        """The menu: Show, the app's items, Quit. An id of 0 is a separator."""
        entries = [(SHOW_ID, "Show")]
        entries += [(FIRST_ITEM_ID + n, label) for n, label in enumerate(self._items.labels())]
        entries += [(0, ""), (QUIT_ID, "Quit")]
        return entries

    def _on_event(self, event: str) -> None:
        if event == "click":
            self._run("show", self._show)
        elif event == "menu":
            self._choose()

    def _choose(self) -> None:
        chosen = self._backend.choose(self.entries())
        if chosen == SHOW_ID:
            self._run("show", self._show)
        elif chosen == QUIT_ID:
            self._run("quit", self._quit)
        elif chosen is not None and chosen >= FIRST_ITEM_ID:
            items = list(self._items)
            index = chosen - FIRST_ITEM_ID
            if index < len(items):
                label, function = items[index]
                self._run(label, function)

    @staticmethod
    def _run(name: str, function: Callable[[], object]) -> None:
        """Run what a click asked for on its own thread, so the icon's thread is never held."""

        def call() -> None:
            try:
                function()
            except Exception:
                logger.exception("The tray item %r failed", name)

        threading.Thread(target=call, name=f"cornea-tray-{name}", daemon=True).start()


# ----- Windows ------------------------------------------------------------------------------


class NotifyIconData(ctypes.Structure):
    """``NOTIFYICONDATAW``, the record ``Shell_NotifyIconW`` takes."""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeout", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class Win32Backend:
    """The icon itself: a hidden window and ``Shell_NotifyIcon``. Windows only."""

    CALLBACK = 0x8001  # WM_APP + 1
    ICON_ID = 1

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._hwnd: int | None = None
        self._error: BaseException | None = None
        self._tooltip = ""
        self._icon: Path | None = None
        self._on_event: Callable[[str], None] = lambda event: None
        self._hicon: Any = None
        self._owns_icon = False
        self._proc: Any = None
        self._restart_message = 0

    def start(self, tooltip: str, icon: Path | None, on_event: Callable[[str], None]) -> None:
        self._tooltip, self._icon, self._on_event = tooltip, icon, on_event
        self._thread = threading.Thread(target=self._run, name="cornea-tray", daemon=True)
        self._thread.start()
        if not self._ready.wait(START_TIMEOUT):
            raise TimeoutError("the tray icon did not appear")
        if self._error is not None:
            raise RuntimeError("the tray icon could not be created") from self._error

    def set_tooltip(self, tooltip: str) -> None:
        self._tooltip = tooltip
        if self._hwnd is not None:
            self._notify(modify=True)

    def stop(self) -> None:

        hwnd, thread = self._hwnd, self._thread
        if hwnd is not None:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostMessageW.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        if thread is not None:
            thread.join(2)

    def choose(self, entries: list[tuple[int, str]]) -> int | None:

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_size_t,
            wintypes.LPCWSTR,
        ]
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.LPVOID,
        ]
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        menu = user32.CreatePopupMenu()
        try:
            for entry_id, label in entries:
                if entry_id == 0:
                    user32.AppendMenuW(menu, 0x0800, 0, None)  # MF_SEPARATOR
                else:
                    user32.AppendMenuW(menu, 0x0000, entry_id, label)  # MF_STRING
            # The menu closes when a click lands elsewhere only if its owner is in front.
            user32.SetForegroundWindow(self._hwnd)
            # TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_BOTTOMALIGN
            chosen = user32.TrackPopupMenu(
                menu, 0x0100 | 0x0002 | 0x0020, point.x, point.y, 0, self._hwnd, None
            )
            user32.PostMessageW(self._hwnd, 0x0000, 0, 0)  # WM_NULL, as the documentation asks
        finally:
            user32.DestroyMenu(menu)
        return int(chosen) or None

    # ----- the icon's thread ----------------------------------------------------------------

    def _run(self) -> None:

        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._create_window(user32)
            self._load_icon()
            self._notify(modify=False)
        except BaseException as exc:
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        message = wintypes.MSG()
        user32.GetMessageW.argtypes = [wintypes.LPMSG, wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.DispatchMessageW.argtypes = [wintypes.LPMSG]
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.DispatchMessageW(ctypes.byref(message))
        self._free_icon()

    def _create_window(self, user32: Any) -> None:

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        wndproc_type = ctypes.WINFUNCTYPE(
            wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        class WndClass(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", wndproc_type),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        user32.DefWindowProcW.restype = wintypes.LPARAM
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WndClass)]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.PostQuitMessage.argtypes = [ctypes.c_int]

        self._restart_message = user32.RegisterWindowMessageW("TaskbarCreated")

        def wndproc(hwnd: Any, msg: int, wparam: int, lparam: int) -> int:
            if msg == self.CALLBACK:
                self._on_mouse(lparam & 0xFFFF)
                return 0
            if msg == self._restart_message and msg:
                self._on_event("restart")
                self._notify(modify=False)  # Explorer restarted: the icon must be added again
                return 0
            if msg == 0x0010:  # WM_CLOSE
                self._remove()
                user32.DestroyWindow(hwnd)
                return 0
            if msg == 0x0002:  # WM_DESTROY
                self._hwnd = None
                user32.PostQuitMessage(0)
                return 0
            return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))

        self._proc = wndproc_type(wndproc)  # kept alive for as long as the window is
        class_name = f"CorneaTray-{id(self)}"
        window_class = WndClass()
        window_class.lpfnWndProc = self._proc
        window_class.hInstance = kernel32.GetModuleHandleW(None)
        window_class.lpszClassName = class_name
        if not user32.RegisterClassW(ctypes.byref(window_class)):
            raise ctypes.WinError(ctypes.get_last_error())
        hwnd = user32.CreateWindowExW(
            0, class_name, "Cornea tray", 0, 0, 0, 0, 0, None, None, window_class.hInstance, None
        )
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self._hwnd = int(hwnd)

    def _on_mouse(self, mouse_message: int) -> None:
        if mouse_message in (0x0202, 0x0203):  # WM_LBUTTONUP, WM_LBUTTONDBLCLK
            self._on_event("click")
        elif mouse_message in (0x0205, 0x007B):  # WM_RBUTTONUP, WM_CONTEXTMENU
            self._on_event("menu")

    def _load_icon(self) -> None:
        """The window's icon, or the system's default application icon."""

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        if self._icon is not None:
            try:
                if self._icon.suffix.lower() == ".ico":
                    handle = user32.LoadImageW(
                        None,
                        str(self._icon),
                        1,
                        0,
                        0,
                        0x0010 | 0x0040,  # LOADFROMFILE|DEFAULTSIZE
                    )
                    if handle:
                        self._hicon, self._owns_icon = handle, True
                        return
                else:
                    from System.Drawing import Bitmap  # type: ignore[import-not-found]

                    self._hicon = Bitmap(str(self._icon)).GetHicon().ToInt64()
                    self._owns_icon = True
                    return
            except Exception:
                logger.warning("Could not load the tray icon from %s", self._icon, exc_info=True)
        user32.LoadIconW.restype = wintypes.HANDLE
        user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        self._hicon, self._owns_icon = user32.LoadIconW(None, 32512), False  # IDI_APPLICATION

    def _free_icon(self) -> None:
        if self._owns_icon and self._hicon:
            user32 = ctypes.WinDLL("user32")
            user32.DestroyIcon.argtypes = [wintypes.HICON]
            user32.DestroyIcon(self._hicon)
        self._hicon = None

    def _notify(self, *, modify: bool) -> None:
        self._call(0x1 if modify else 0x0)  # NIM_MODIFY, NIM_ADD

    def _remove(self) -> None:
        self._call(0x2)  # NIM_DELETE

    def _call(self, action: int) -> None:
        data = NotifyIconData()
        data.cbSize = ctypes.sizeof(NotifyIconData)
        data.hWnd = self._hwnd
        data.uID = self.ICON_ID
        data.uFlags = 0x1 | 0x2 | 0x4  # NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = self.CALLBACK
        data.hIcon = self._hicon
        data.szTip = self._tooltip[:MAX_TOOLTIP]
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NotifyIconData)]
        if not shell32.Shell_NotifyIconW(action, ctypes.byref(data)) and action != 0x2:
            raise ctypes.WinError(ctypes.get_last_error())
