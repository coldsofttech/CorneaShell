"""Allow one copy of an app at a time, and let a second copy wake the first.

The lock is a named Windows mutex, so it is released by the system if the app crashes and there
is never a stale lock. The first copy also listens on a private loopback port and writes where, with
a secret, to the app's data folder. A second copy reads that, asks the first to come to the front
and exits.
"""

import contextlib
import json
import secrets
import socket
import threading
from collections.abc import Callable
from typing import Any

from cornea.core.app.appdata import AppData

ERROR_ALREADY_EXISTS = 183
CONNECT_TIMEOUT = 2.0
MAX_LINE = 256
INFO_FILE = "instance.json"


class AlreadyRunning(RuntimeError):
    """Another copy of the app is already running."""

    def __init__(self, app_id: str, *, activated: bool) -> None:
        self.activated = activated
        detail = "brought its window to the front" if activated else "could not reach its window"
        super().__init__(f"{app_id!r} is already running; {detail}.")


class InstanceLock:
    """The single-instance lock of one app id."""

    def __init__(self, app_id: str) -> None:
        self.app_id = app_id
        self._handle: Any = None
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._secret = secrets.token_urlsafe(24)

    def acquire(self) -> bool:
        """Take the lock. ``False`` means another copy of this app id holds it."""
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        handle = kernel32.CreateMutexW(None, False, f"Local\\Cornea-{self.app_id}")
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def serve(self, on_activate: Callable[[], None]) -> None:
        """Listen for a second copy asking this one to come to the front."""
        listener = socket.create_server(("127.0.0.1", 0))
        listener.settimeout(0.2)
        self._listener = listener
        info = {"port": listener.getsockname()[1], "secret": self._secret}
        (AppData.data_dir(self.app_id) / INFO_FILE).write_text(json.dumps(info), encoding="utf-8")
        self._thread = threading.Thread(
            target=self._listen, args=(listener, on_activate), name="cornea-instance", daemon=True
        )
        self._thread.start()

    def release(self) -> None:
        """Let go of the lock and stop listening. Safe to call more than once."""
        listener, thread, handle = self._listener, self._thread, self._handle
        self._listener = self._thread = self._handle = None
        if listener is not None:
            listener.close()
        if thread is not None:
            thread.join(2)
        if listener is not None:
            with contextlib.suppress(OSError):
                (AppData.data_dir(self.app_id) / INFO_FILE).unlink()
        if handle is not None:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32")
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle(handle)

    def _listen(self, listener: socket.socket, on_activate: Callable[[], None]) -> None:
        expected = f"ACTIVATE {self._secret}".encode()
        while self._listener is listener:
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(CONNECT_TIMEOUT)
                try:
                    received = connection.makefile("rb").readline(MAX_LINE).strip()
                except OSError:
                    continue
                if secrets.compare_digest(received, expected):
                    with contextlib.suppress(Exception):  # a failed focus must not stop the loop
                        on_activate()
                    with contextlib.suppress(OSError):
                        connection.sendall(b"OK\n")


def activate_existing(app_id: str) -> bool:
    """Ask the running copy of ``app_id`` to come to the front. ``True`` if it did."""
    try:
        info: Any = json.loads((AppData.data_dir(app_id) / INFO_FILE).read_text(encoding="utf-8"))
        with socket.create_connection(("127.0.0.1", int(info["port"])), CONNECT_TIMEOUT) as client:
            client.sendall(f"ACTIVATE {info['secret']}\n".encode())
            return client.makefile("r", encoding="utf-8").readline().strip() == "OK"
    except (OSError, ValueError, KeyError, TypeError):
        return False
