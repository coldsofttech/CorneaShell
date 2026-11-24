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
from cornea.core.app.launch import LaunchRequest

ERROR_ALREADY_EXISTS = 183
CONNECT_TIMEOUT = 2.0
MAX_LINE = 256
MAX_LAUNCH_LINE = 65536
"""A launch request carries the new copy's arguments, so its line can be longer."""
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

    def serve(
        self,
        on_activate: Callable[[], None],
        on_launch: Callable[[LaunchRequest], None] | None = None,
    ) -> None:
        """Listen for a second copy asking this one to come to the front.

        ``on_launch`` is also given the arguments a second copy was started with, after
        ``on_activate`` has run.
        """
        listener = socket.create_server(("127.0.0.1", 0))
        listener.settimeout(0.2)
        self._listener = listener
        info = {"port": listener.getsockname()[1], "secret": self._secret}
        (AppData.data_dir(self.app_id) / INFO_FILE).write_text(json.dumps(info), encoding="utf-8")
        self._thread = threading.Thread(
            target=self._listen,
            args=(listener, on_activate, on_launch),
            name="cornea-instance",
            daemon=True,
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

    @staticmethod
    def _launch_request(received: bytes, prefix: bytes) -> LaunchRequest | None:
        """The request in a ``LAUNCH <secret> <json>`` line, or ``None`` if it is not a valid one.

        The secret is compared in constant time; a wrong secret or a damaged body is ignored.
        """
        head, body = received[: len(prefix)], received[len(prefix) :]
        if len(head) != len(prefix) or not secrets.compare_digest(head, prefix):
            return None
        try:
            return LaunchRequest.from_json(json.loads(body.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            return None

    def _listen(
        self,
        listener: socket.socket,
        on_activate: Callable[[], None],
        on_launch: Callable[[LaunchRequest], None] | None = None,
    ) -> None:
        expected = f"ACTIVATE {self._secret}".encode()
        launch_prefix = f"LAUNCH {self._secret} ".encode()
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
                    received = connection.makefile("rb").readline(MAX_LAUNCH_LINE).strip()
                except OSError:
                    continue
                request = self._launch_request(received, launch_prefix)
                if request is not None:
                    with contextlib.suppress(Exception):
                        on_activate()
                    if on_launch is not None:
                        with contextlib.suppress(Exception):  # the app's handler must not stop us
                            on_launch(request)
                    with contextlib.suppress(OSError):
                        connection.sendall(b"OK\n")
                elif len(received) <= MAX_LINE and secrets.compare_digest(received, expected):
                    with contextlib.suppress(Exception):  # a failed focus must not stop the loop
                        on_activate()
                    with contextlib.suppress(OSError):
                        connection.sendall(b"OK\n")


def activate_existing(app_id: str, launch: LaunchRequest | None = None) -> bool:
    """Ask the running copy of ``app_id`` to come to the front. ``True`` if it did.

    With ``launch`` the running copy is also told what this one was started with.
    """
    try:
        info: Any = json.loads((AppData.data_dir(app_id) / INFO_FILE).read_text(encoding="utf-8"))
        with socket.create_connection(("127.0.0.1", int(info["port"])), CONNECT_TIMEOUT) as client:
            if launch is None:
                client.sendall(f"ACTIVATE {info['secret']}\n".encode())
            else:
                body = json.dumps(launch.as_json(), separators=(",", ":"))
                client.sendall(f"LAUNCH {info['secret']} {body}\n".encode())
            return client.makefile("r", encoding="utf-8").readline().strip() == "OK"
    except (OSError, ValueError, KeyError, TypeError):
        return False
