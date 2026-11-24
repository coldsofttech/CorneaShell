"""The Windows taskbar button: a progress bar, an overlay badge and a jump list.

All three go through the Windows shell's own COM interfaces with ``ctypes``, so there is nothing
extra to install. Every call must run on the window's UI thread; the window controller takes care
of that.

- **Progress** is drawn on the app's taskbar button (``ITaskbarList3``).
- **The badge** is a small red circle with a count (or a plain dot) over the button's icon. It is
  drawn here, pixel by pixel, so no font or image file is needed.
- **The jump list** is the menu of tasks on the button's right-click menu
  (``ICustomDestinationList``). Choosing one starts the app again with a private argument
  (:data:`JUMP_ARGUMENT`). A running copy is told instead, when the app allows one copy.
"""

import contextlib
import ctypes
import re
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any

from cornea.core.window.window import Unavailable

MAX_ITEMS = 10
MAX_ID = 64
MAX_TITLE = 64
MAX_DESCRIPTION = 256
MAX_COUNT = 99
ITEM_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")
JUMP_ARGUMENT = "--cornea-jump"
"""The command-line argument a jump list entry starts the app with: ``--cornea-jump=<id>``."""

PROGRESS_STATES = {"none": 0x0, "indeterminate": 0x1, "normal": 0x2, "error": 0x4, "paused": 0x8}
BADGE_SIZE = 32
_BADGE_COLOR = (0xD1, 0x34, 0x38)  # red, as red, green, blue
_GLYPHS = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
}


@dataclass(frozen=True, slots=True)
class JumpItem:
    """One entry in the jump list: a task the person can start from the taskbar button.

    Example:
        >>> JumpItem("new-note", "New note").title
        'New note'
    """

    id: str
    """What the page and your code hear when it is chosen (``cornea:jump-list-click``)."""
    title: str
    """The text of the entry."""
    description: str | None = None
    """The tooltip of the entry."""


class Taskbar:
    """Checks what is asked for, and shows it on one window's taskbar button."""

    def __init__(self, app_id: str | None, handle: Callable[[], int]) -> None:
        self.app_id = app_id
        self._handle = handle
        self._list: Any = None
        self._badge_icon: Any = None

    # ----- what is allowed ---------------------------------------------------------------------

    @staticmethod
    def check_progress(state: object, value: object = None) -> tuple[str, float | None]:
        """Refuse an unknown state or a value outside 0 to 100.

        Raises:
            ValueError: With what is wrong.
        """
        if not isinstance(state, str) or state not in PROGRESS_STATES:
            raise ValueError(f"state must be one of {', '.join(PROGRESS_STATES)}")
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 100
        ):
            raise ValueError("value must be a number from 0 to 100")
        if state == "normal" and value is None:
            raise ValueError("value is needed for the 'normal' state")
        return state, None if value is None else float(value)

    @staticmethod
    def check_badge(count: object) -> str | None:
        """The text to draw for a badge: a count, a dot (``True``) or nothing (``None``/0).

        Raises:
            ValueError: With what is wrong.
        """
        if count is None or count is False:
            return None
        if count is True:
            return ""
        if not isinstance(count, int) or count < 0:
            raise ValueError("count must be a whole number, True for a dot, or None to clear it")
        if count == 0:
            return None
        return str(count) if count <= MAX_COUNT else f"{MAX_COUNT}+"

    @staticmethod
    def check_items(items: object) -> list[JumpItem]:
        """Turn what was given into a list of :class:`JumpItem`, or say what is wrong.

        Raises:
            ValueError: With what is wrong.
        """
        if not isinstance(items, Sequence) or isinstance(items, str | bytes):
            raise ValueError("items must be a list")
        if len(items) > MAX_ITEMS:
            raise ValueError(f"a jump list can have at most {MAX_ITEMS} items")
        checked: list[JumpItem] = []
        for entry in items:
            if isinstance(entry, JumpItem):
                item = entry
            elif isinstance(entry, Mapping):
                unknown = set(entry) - {"id", "title", "description"}
                if unknown:
                    raise ValueError(f"unknown item fields: {sorted(map(str, unknown))}")
                item = JumpItem(
                    entry.get("id"),  # type: ignore[arg-type]
                    entry.get("title"),  # type: ignore[arg-type]
                    entry.get("description"),
                )
            else:
                raise ValueError("each item must be a JumpItem or an object with id and title")
            Taskbar._check_item(item)
            checked.append(item)
        if len({item.id for item in checked}) != len(checked):
            raise ValueError("item ids must be unique")
        return checked

    @staticmethod
    def _check_item(item: JumpItem) -> None:
        if (
            not isinstance(item.id, str)
            or not item.id
            or len(item.id) > MAX_ID
            or not ITEM_ID.match(item.id)
        ):
            raise ValueError(
                f"item id must be up to {MAX_ID} letters, digits and . _ : - characters"
            )
        if not isinstance(item.title, str) or not item.title.strip():
            raise ValueError("item title must be a non-empty string")
        if len(item.title) > MAX_TITLE or any(ord(c) < 32 for c in item.title):
            raise ValueError(f"item title can have at most {MAX_TITLE} plain characters")
        if item.description is not None and (
            not isinstance(item.description, str)
            or len(item.description) > MAX_DESCRIPTION
            or any(ord(c) < 32 for c in item.description)
        ):
            raise ValueError(f"item description can have at most {MAX_DESCRIPTION} characters")

    # ----- the badge picture -------------------------------------------------------------------

    @staticmethod
    def badge_pixels(text: str) -> bytes:
        """The badge as ``BADGE_SIZE`` squared BGRA pixels: a red disc with white ``text``."""
        size = BADGE_SIZE
        pixels = bytearray(size * size * 4)
        centre, radius = (size - 1) / 2, size / 2 - 0.5
        for y in range(size):
            for x in range(size):
                distance = ((x - centre) ** 2 + (y - centre) ** 2) ** 0.5
                coverage = max(0.0, min(1.0, radius - distance + 0.5))
                if coverage:
                    Taskbar._put(pixels, x, y, _BADGE_COLOR, round(255 * coverage))
        if text:
            Taskbar._draw_text(pixels, text)
        return bytes(pixels)

    @staticmethod
    def _put(pixels: bytearray, x: int, y: int, rgb: tuple[int, int, int], alpha: int) -> None:
        offset = (y * BADGE_SIZE + x) * 4
        pixels[offset : offset + 4] = bytes((rgb[2], rgb[1], rgb[0], alpha))

    @staticmethod
    def _draw_text(pixels: bytearray, text: str) -> None:
        scale = 2 if len(text) <= 2 else 1
        width = len(text) * 5 * scale + (len(text) - 1) * scale
        left = (BADGE_SIZE - width) // 2
        top = (BADGE_SIZE - 7 * scale) // 2
        for index, char in enumerate(text):
            glyph = _GLYPHS[char]
            origin = left + index * 6 * scale
            for row, line in enumerate(glyph):
                for column, bit in enumerate(line):
                    if bit != "1":
                        continue
                    for dy in range(scale):
                        for dx in range(scale):
                            Taskbar._put(
                                pixels,
                                origin + column * scale + dx,
                                top + row * scale + dy,
                                (255, 255, 255),
                                255,
                            )

    # ----- the jump list's command -------------------------------------------------------------

    @staticmethod
    def launch_command(item_id: str) -> tuple[str, str]:
        """The program and the arguments that start this app again for a jump list entry."""
        arguments = [a for a in sys.orig_argv[1:] if not a.startswith(JUMP_ARGUMENT)]
        arguments = [*arguments, f"{JUMP_ARGUMENT}={item_id}"]
        return sys.executable, subprocess.list2cmdline(arguments)

    @staticmethod
    def take_launch_item(argv: list[str] | None = None) -> str | None:
        """The jump list id this copy was started with, taken out of ``argv`` so the app's own
        argument parsing never sees it. ``None`` for a normal start."""
        arguments = sys.argv if argv is None else argv
        found: str | None = None
        for argument in list(arguments[1:]):
            if argument.startswith(f"{JUMP_ARGUMENT}="):
                arguments.remove(argument)
                value = argument.split("=", 1)[1]
                if len(value) <= MAX_ID and ITEM_ID.match(value):
                    found = value
        return found

    # ----- showing it --------------------------------------------------------------------------

    def set_progress(self, state: str, value: float | None = None) -> None:
        """Show progress on the taskbar button. ``value`` is 0 to 100."""
        state, value = self.check_progress(state, value)
        self._require_windows()
        taskbar = self._taskbar()
        hwnd = self._handle()
        if value is not None:
            _vcall(taskbar, 9, wintypes.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong)(
                hwnd, round(value * 10), 1000
            )
        _vcall(taskbar, 10, wintypes.HWND, ctypes.c_int)(hwnd, PROGRESS_STATES[state])

    def set_badge(self, count: object) -> None:
        """Put a count (or a dot) over the button's icon, or take it off with ``None``."""
        text = self.check_badge(count)
        self._require_windows()
        taskbar = self._taskbar()
        hwnd = self._handle()
        old = self._badge_icon
        if text is None:
            _vcall(taskbar, 18, wintypes.HWND, ctypes.c_void_p, wintypes.LPCWSTR)(hwnd, None, None)
            self._badge_icon = None
        else:
            icon = _make_icon(self.badge_pixels(text))
            label = "notification" if not text else f"{text} notifications"
            _vcall(taskbar, 18, wintypes.HWND, ctypes.c_void_p, wintypes.LPCWSTR)(hwnd, icon, label)
            self._badge_icon = icon
        if old is not None:
            ctypes.WinDLL("user32").DestroyIcon(ctypes.c_void_p(old))

    def set_jump_list(self, items: object) -> None:
        """Replace the jump list's tasks. An empty list removes them."""
        checked = self.check_items(items)
        self._require_windows()
        _write_jump_list(self.app_id, checked)

    # ----- internals ---------------------------------------------------------------------------

    @staticmethod
    def _require_windows() -> None:
        if sys.platform != "win32":
            raise Unavailable("The taskbar only works on Windows for now.")

    def _taskbar(self) -> Any:
        if self._list is None:
            created = _create(_CLSID_TASKBAR_LIST, _IID_TASKBAR_LIST3)
            _vcall(created, 3)()  # HrInit
            self._list = created
        return self._list


# ----- COM, through ctypes --------------------------------------------------------------------


class _Guid(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]


def _guid(text: str) -> _Guid:
    guid = _Guid()
    guid.bytes[:] = uuid.UUID(text).bytes_le
    return guid


_CLSID_TASKBAR_LIST = "56FDF344-FD6D-11D0-958A-006097C9A090"
_IID_TASKBAR_LIST3 = "EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF"
_CLSID_DESTINATION_LIST = "77F10CF0-3DB5-4966-B520-B7C54FD35ED6"
_IID_DESTINATION_LIST = "6332DEBF-87B5-4670-90C0-5E57B408A49E"
_CLSID_OBJECT_COLLECTION = "2D3468C1-36A7-43B6-AC24-D3F02FD9607A"
_IID_OBJECT_COLLECTION = "5632B1A4-E38A-400A-928A-D4CD63230295"
_IID_OBJECT_ARRAY = "92CA9DCD-5622-4BBA-A805-5E9F541BD8C9"
_CLSID_SHELL_LINK = "00021401-0000-0000-C000-000000000046"
_IID_SHELL_LINK = "000214F9-0000-0000-C000-000000000046"
_IID_PROPERTY_STORE = "886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"
_PKEY_TITLE = ("F29F85E0-4FF9-1068-AB91-08002B27B3D9", 2)
_CLSCTX_INPROC_SERVER = 1


def _vcall(obj: Any, index: int, *types: Any) -> Callable[..., None]:
    """The method at ``index`` of a COM object's table, as a function that checks the result."""
    pointer = ctypes.c_void_p(obj) if not isinstance(obj, ctypes.c_void_p) else obj
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0]
    entry = ctypes.cast(table, ctypes.POINTER(ctypes.c_void_p))[index]
    function = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(entry)

    def call(*arguments: Any) -> None:
        result = function(pointer, *arguments)
        if result < 0:
            raise OSError(f"Windows refused the taskbar call (0x{result & 0xFFFFFFFF:08X})")

    return call


def _create(clsid: str, iid: str) -> ctypes.c_void_p:
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitialize(None)  # harmless when the thread already has COM
    found = ctypes.c_void_p()
    result = ole32.CoCreateInstance(
        ctypes.byref(_guid(clsid)),
        None,
        _CLSCTX_INPROC_SERVER,
        ctypes.byref(_guid(iid)),
        ctypes.byref(found),
    )
    if result < 0 or not found.value:
        raise OSError(f"Windows could not create the taskbar object (0x{result & 0xFFFFFFFF:08X})")
    return found


def _query(obj: ctypes.c_void_p, iid: str) -> ctypes.c_void_p:
    found = ctypes.c_void_p()
    _vcall(obj, 0, ctypes.c_void_p, ctypes.c_void_p)(ctypes.byref(_guid(iid)), ctypes.byref(found))
    return found


def _release(*objects: ctypes.c_void_p) -> None:
    for obj in objects:
        if obj.value:
            _vcall(obj, 2)()


class _IconInfo(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HANDLE),
        ("hbmColor", wintypes.HANDLE),
    ]


def _make_icon(bgra: bytes) -> int:
    """An icon handle from ``BADGE_SIZE`` squared BGRA pixels. The caller destroys it."""
    gdi32, user32 = ctypes.WinDLL("gdi32"), ctypes.WinDLL("user32")
    gdi32.CreateBitmap.restype = wintypes.HANDLE
    user32.CreateIconIndirect.restype = wintypes.HANDLE
    color = gdi32.CreateBitmap(BADGE_SIZE, BADGE_SIZE, 1, 32, bgra)
    mask = gdi32.CreateBitmap(BADGE_SIZE, BADGE_SIZE, 1, 1, None)
    try:
        info = _IconInfo(True, 0, 0, mask, color)
        icon = user32.CreateIconIndirect(ctypes.byref(info))
        if not icon:
            raise ctypes.WinError()
        return int(icon)
    finally:
        gdi32.DeleteObject(ctypes.c_void_p(color))
        gdi32.DeleteObject(ctypes.c_void_p(mask))


class _PropKey(ctypes.Structure):
    _fields_ = [("fmtid", _Guid), ("pid", wintypes.DWORD)]


def _make_link(item: JumpItem) -> ctypes.c_void_p:
    program, arguments = Taskbar.launch_command(item.id)
    link = _create(_CLSID_SHELL_LINK, _IID_SHELL_LINK)
    try:
        _vcall(link, 20, wintypes.LPCWSTR)(program)  # SetPath
        _vcall(link, 11, wintypes.LPCWSTR)(arguments)  # SetArguments
        _vcall(link, 17, wintypes.LPCWSTR, ctypes.c_int)(program, 0)  # SetIconLocation
        if item.description:
            _vcall(link, 7, wintypes.LPCWSTR)(item.description)  # SetDescription
        store = _query(link, _IID_PROPERTY_STORE)
        try:
            propsys, ole32 = ctypes.WinDLL("propsys"), ctypes.WinDLL("ole32")
            variant = (ctypes.c_byte * 24)()  # a PROPVARIANT
            propsys.InitPropVariantFromString(item.title, ctypes.byref(variant))
            try:
                key = _PropKey(_guid(_PKEY_TITLE[0]), _PKEY_TITLE[1])
                _vcall(store, 6, ctypes.c_void_p, ctypes.c_void_p)(
                    ctypes.byref(key), ctypes.byref(variant)
                )
                _vcall(store, 7)()
            finally:
                ole32.PropVariantClear(ctypes.byref(variant))
        finally:
            _release(store)
    except BaseException:
        _release(link)
        raise
    return link


def _write_jump_list(app_id: str | None, items: list[JumpItem]) -> None:
    destinations = _create(_CLSID_DESTINATION_LIST, _IID_DESTINATION_LIST)
    try:
        if app_id:
            _vcall(destinations, 3, wintypes.LPCWSTR)(app_id)  # SetAppID
        slots, removed = ctypes.c_uint(), ctypes.c_void_p()
        _vcall(destinations, 4, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
            ctypes.byref(slots), ctypes.byref(_guid(_IID_OBJECT_ARRAY)), ctypes.byref(removed)
        )  # BeginList
        _release(removed)
        collection = _create(_CLSID_OBJECT_COLLECTION, _IID_OBJECT_COLLECTION)
        try:
            for item in items:
                link = _make_link(item)
                try:
                    _vcall(collection, 5, ctypes.c_void_p)(link)  # AddObject
                finally:
                    _release(link)
            array = _query(collection, _IID_OBJECT_ARRAY)
            try:
                _vcall(destinations, 7, ctypes.c_void_p)(array)  # AddUserTasks
            finally:
                _release(array)
        finally:
            _release(collection)
        _vcall(destinations, 8)()  # CommitList
    except BaseException:
        with contextlib.suppress(OSError):
            _vcall(destinations, 11)()  # AbortList
        raise
    finally:
        _release(destinations)
