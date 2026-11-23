"""The Windows clipboard, as plain text.

Used by the opt-in ``clipboard_read`` and ``clipboard_write`` actions. Only text is handled: other
formats on the clipboard (images, files) are neither read nor changed except that writing text
replaces whatever was there. It uses the Win32 clipboard calls directly, so it needs no extra.
"""

import sys
import time
from typing import Any

MAX_TEXT = 1_000_000
"""The most characters a page can put on the clipboard in one call."""
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
_OPEN_TRIES = 10
_OPEN_PAUSE = 0.02


class ClipboardError(OSError):
    """The clipboard could not be read or written, for example because another program holds it."""


class Clipboard:
    """Reads and writes the system clipboard as text. Windows only."""

    @staticmethod
    def check(text: object) -> str:
        """Refuse anything that is not a string of a sensible size.

        Raises:
            ValueError: With what is wrong.
        """
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        if len(text) > MAX_TEXT:
            raise ValueError(f"text can have at most {MAX_TEXT} characters")
        if "\0" in text:
            raise ValueError("text must not contain null characters")
        return text

    @staticmethod
    def read() -> str | None:
        """The text on the clipboard, or ``None`` when it holds no text."""
        user32, kernel32 = Clipboard._libraries()
        Clipboard._open(user32)
        try:
            if not user32.IsClipboardFormatAvailable(_CF_UNICODETEXT):
                return None
            handle = user32.GetClipboardData(_CF_UNICODETEXT)
            if not handle:
                return None
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                raise ClipboardError("the clipboard text could not be read")
            try:
                import ctypes

                return ctypes.wstring_at(pointer)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    @staticmethod
    def write(text: str) -> None:
        """Replace the clipboard's contents with ``text``."""
        import ctypes

        Clipboard.check(text)
        user32, kernel32 = Clipboard._libraries()
        data = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(data)
        handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, size)
        if not handle:
            raise ClipboardError("there is no memory to copy the text")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            raise ClipboardError("the text could not be copied")
        ctypes.memmove(pointer, data, size)
        kernel32.GlobalUnlock(handle)
        try:
            Clipboard._open(user32)
        except ClipboardError:
            kernel32.GlobalFree(handle)
            raise
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(_CF_UNICODETEXT, handle):
                kernel32.GlobalFree(handle)
                raise ClipboardError("the text could not be put on the clipboard")
            # The system owns the memory now.
        finally:
            user32.CloseClipboard()

    @staticmethod
    def _open(user32: Any) -> None:
        # Another program can hold the clipboard for a moment, so try a few times.
        for _ in range(_OPEN_TRIES):
            if user32.OpenClipboard(None):
                return
            time.sleep(_OPEN_PAUSE)
        raise ClipboardError("the clipboard is in use by another program")

    @staticmethod
    def _libraries() -> tuple[Any, Any]:
        if sys.platform != "win32":
            raise RuntimeError("The clipboard only works on Windows for now.")
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
        user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.restype = wintypes.HGLOBAL
        return user32, kernel32
