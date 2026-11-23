"""Global hotkeys: keyboard shortcuts that fire even when the window is not focused.

Only Python code registers them (``Shell.register_hotkey``), so a page cannot grab keys by
itself and nothing is registered unless the app asks. Windows keeps a global shortcut for one
program at a time, so a shortcut another program already holds is refused with a clear error.

The shortcuts are registered with the Win32 ``RegisterHotKey`` call on a thread of their own,
which waits for the keys with a message loop. The part that talks to Windows is
:class:`Win32Hotkeys`; :class:`Hotkeys` holds the rules (parsing, duplicates, callbacks) and works
with any backend, which is how it is tested on other platforms.
"""

import logging
import queue
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
"""Holding the keys down fires the shortcut once, not repeatedly."""

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
    "meta": MOD_WIN,
}
_CANONICAL = ((MOD_CONTROL, "ctrl"), (MOD_ALT, "alt"), (MOD_SHIFT, "shift"), (MOD_WIN, "win"))

_NAMED_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
}
_KEY_ALIASES = {"return": "enter", "escape": "esc"}


@dataclass(frozen=True, slots=True)
class Hotkey:
    """A parsed shortcut: the modifiers, the virtual key and its canonical name."""

    name: str
    modifiers: int
    key: int


def parse_hotkey(text: object) -> Hotkey:
    """Read a shortcut such as ``"ctrl+alt+space"`` or ``"Win+Shift+F12"``.

    A shortcut has at least one of ``ctrl``, ``alt`` or ``win`` (a bare letter or ``shift`` alone
    would take over typing), and exactly one key: a letter, a digit, ``f1`` to ``f24`` or a name
    such as ``space``, ``enter``, ``tab``, ``esc``, ``home``, ``left``. The canonical name is
    lowercase with the modifiers in a fixed order, and it is what the page receives.

    Raises:
        ValueError: With what is wrong.

    Example:
        >>> parse_hotkey("Alt+Ctrl+Space").name
        'ctrl+alt+space'
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("a hotkey must be a non-empty string such as 'ctrl+alt+space'")
    parts = [part.strip().lower() for part in text.split("+")]
    if not all(parts):
        raise ValueError(f"not a hotkey: {text!r}")
    *held, key = parts
    modifiers = 0
    for part in held:
        if part not in _MODIFIERS:
            raise ValueError(f"unknown modifier {part!r} in {text!r}; use ctrl, alt, shift or win")
        flag = _MODIFIERS[part]
        if modifiers & flag:
            raise ValueError(f"{part!r} is repeated in {text!r}")
        modifiers |= flag
    if not modifiers & (MOD_CONTROL | MOD_ALT | MOD_WIN):
        raise ValueError(f"{text!r} needs ctrl, alt or win, or it would take over typing")
    if key in _MODIFIERS:
        raise ValueError(f"{text!r} ends with a modifier; it needs a key such as space or a letter")
    code = _key_code(key, text)
    key = _KEY_ALIASES.get(key, key)
    names = [name for flag, name in _CANONICAL if modifiers & flag]
    return Hotkey("+".join([*names, key]), modifiers, code)


def _key_code(key: str, text: str) -> int:
    if len(key) == 1 and "a" <= key <= "z":
        return ord(key.upper())
    if len(key) == 1 and "0" <= key <= "9":
        return ord(key)
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return 0x70 + int(key[1:]) - 1
    if key in _NAMED_KEYS:
        return _NAMED_KEYS[key]
    raise ValueError(f"unknown key {key!r} in {text!r}")


class HotkeyBackend(Protocol):
    """What :class:`Hotkeys` needs from the system."""

    def register(self, hotkey: Hotkey, on_press: Callable[[], None]) -> object:
        """Register the shortcut and return a handle. Raises ``OSError`` if it is taken."""
        ...

    def unregister(self, handle: object) -> None: ...

    def close(self) -> None:
        """Release everything."""
        ...


class Hotkeys:
    """The shortcuts of one app: parses them, refuses duplicates and runs their callbacks.

    Example:
        >>> class Backend:
        ...     def register(self, hotkey, on_press):
        ...         return hotkey.name
        ...     def unregister(self, handle): ...
        ...     def close(self): ...
        >>> hotkeys = Hotkeys(lambda name: None, Backend())
        >>> hotkeys.register("Alt+Ctrl+Space")
        'ctrl+alt+space'
        >>> hotkeys.registered()
        ['ctrl+alt+space']
    """

    def __init__(
        self, on_press: Callable[[str], None], backend: HotkeyBackend | None = None
    ) -> None:
        self._on_press = on_press
        self._backend = backend
        self._handlers: dict[str, Callable[[], None] | None] = {}
        self._handles: dict[str, object] = {}
        self._lock = threading.Lock()

    def register(self, hotkey: str, handler: Callable[[], None] | None = None) -> str:
        """Register ``hotkey``; ``handler`` runs on each press, and the page is told as well.

        Returns the canonical name.

        Raises:
            ValueError: If the shortcut is not allowed or is already registered here.
            RuntimeError: If Windows refuses it, usually because another program holds it.
        """
        parsed = parse_hotkey(hotkey)
        with self._lock:
            if parsed.name in self._handles:
                raise ValueError(f"{parsed.name!r} is already registered")
            backend = self._backend_or_default()
            try:
                handle = backend.register(parsed, lambda: self._pressed(parsed.name))
            except OSError as exc:
                raise RuntimeError(
                    f"{parsed.name!r} could not be registered; another program may already "
                    f"use it ({exc})"
                ) from exc
            self._handles[parsed.name] = handle
            self._handlers[parsed.name] = handler
        logger.debug("Registered the global hotkey %s", parsed.name)
        return parsed.name

    def unregister(self, hotkey: str) -> bool:
        """Remove a shortcut. Returns whether it was registered."""
        name = parse_hotkey(hotkey).name
        with self._lock:
            handle = self._handles.pop(name, None)
            self._handlers.pop(name, None)
            if handle is None or self._backend is None:
                return False
            self._backend.unregister(handle)
        logger.debug("Removed the global hotkey %s", name)
        return True

    def registered(self) -> list[str]:
        """The registered shortcuts, in the order they were added."""
        with self._lock:
            return list(self._handles)

    def close(self) -> None:
        """Remove every shortcut and stop listening. Safe to call more than once."""
        with self._lock:
            backend, self._backend = self._backend, None
            self._handles.clear()
            self._handlers.clear()
        if backend is not None:
            backend.close()

    def _backend_or_default(self) -> HotkeyBackend:
        if self._backend is None:
            self._backend = Win32Hotkeys()
        return self._backend

    def _pressed(self, name: str) -> None:
        handler = self._handlers.get(name)
        if handler is not None:
            try:
                handler()
            except Exception:
                logger.exception("The handler for the hotkey %s raised", name)
        try:
            self._on_press(name)
        except Exception:
            logger.exception("Could not tell the page about the hotkey %s", name)


WM_HOTKEY = 0x0312
WM_APP = 0x8000
_WM_REGISTER = WM_APP + 1
_WM_UNREGISTER = WM_APP + 2
_WM_QUIT = 0x0012


class Win32Hotkeys:
    """``RegisterHotKey`` on a thread that waits for the keys. Windows only.

    A shortcut belongs to the thread that registered it, so every call is handed to that thread
    and answered when it has run.
    """

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Global hotkeys only work on Windows for now.")
        self._requests: queue.Queue[tuple[str, Any, queue.Queue[Any]]] = queue.Queue()
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 1
        self._thread_id = 0
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="cornea-hotkeys", daemon=True)
        self._thread.start()
        if not self._ready.wait(5.0):
            raise RuntimeError("the hotkey listener did not start")

    def register(self, hotkey: Hotkey, on_press: Callable[[], None]) -> int:
        return int(self._ask("register", (hotkey, on_press)))

    def unregister(self, handle: object) -> None:
        self._ask("unregister", handle)

    def close(self) -> None:
        if self._thread.is_alive():
            self._post(_WM_QUIT)
            self._thread.join(2.0)

    # ----- the listener thread ---------------------------------------------------------------

    def _ask(self, kind: str, payload: Any) -> Any:
        answer: queue.Queue[Any] = queue.Queue(maxsize=1)
        self._requests.put((kind, payload, answer))
        self._post(_WM_REGISTER if kind == "register" else _WM_UNREGISTER)
        result = answer.get(timeout=5.0)
        if isinstance(result, BaseException):
            raise result
        return result

    def _post(self, message: int) -> None:
        import ctypes

        ctypes.WinDLL("user32").PostThreadMessageW(self._thread_id, message, 0, 0)

    def _loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32")
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        self._thread_id = kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)  # creates the message queue
        self._ready.set()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY:
                callback = self._callbacks.get(int(message.wParam))
                if callback is not None:
                    self._run(callback)
            elif message.message in (_WM_REGISTER, _WM_UNREGISTER):
                self._serve_request(user32)
        for hotkey_id in list(self._callbacks):
            user32.UnregisterHotKey(None, hotkey_id)
        self._callbacks.clear()

    @staticmethod
    def _run(callback: Callable[[], None]) -> None:
        # A press can start slow work (showing the window); keep the listener free for the next.
        threading.Thread(target=callback, name="cornea-hotkey-press", daemon=True).start()

    def _serve_request(self, user32: Any) -> None:
        import ctypes

        kind, payload, answer = self._requests.get_nowait()
        try:
            if kind == "register":
                hotkey, on_press = payload
                hotkey_id = self._next_id
                if not user32.RegisterHotKey(
                    None, hotkey_id, hotkey.modifiers | MOD_NOREPEAT, hotkey.key
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                self._next_id += 1
                self._callbacks[hotkey_id] = on_press
                answer.put(hotkey_id)
            else:
                user32.UnregisterHotKey(None, payload)
                self._callbacks.pop(payload, None)
                answer.put(None)
        except BaseException as exc:
            answer.put(exc)
