"""Start a dev-server command, wait until it listens, and stop it with everything it started.

On Windows the command runs inside a job object that is set to kill its members when the last
handle closes. ``npm run dev`` starts ``node`` as a child; stopping only ``npm`` would leave the
server running. With the job, stopping (or Cornea crashing) ends the whole tree.
"""

import collections
import contextlib
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cornea.core.sources import Process

POLL_INTERVAL = 0.1
OUTPUT_LINES = 40
STOP_TIMEOUT = 5.0


class _Job:
    """A Windows job object that kills everything inside it when closed."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("a", "b", "c", "d", "e", "f")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32 = kernel32
        self._handle = kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def add(self, process: "subprocess.Popen[str]") -> None:
        import ctypes

        if not self._kernel32.AssignProcessToJobObject(self._handle, int(process._handle)):  # type: ignore[attr-defined]
            raise ctypes.WinError(ctypes.get_last_error())

    def kill(self) -> None:
        if self._handle:
            self._kernel32.TerminateJobObject(self._handle, 1)
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def _listening(host: str, port: int) -> bool:
    try:
        socket.create_connection((host, port), timeout=0.5).close()
    except OSError:
        return False
    return True


class ProcessRunner:
    """Runs one :class:`~cornea.core.sources.Process` and tells when it is ready."""

    def __init__(self, source: Process) -> None:
        self.source = source
        parts = urlsplit(source.url)
        self.host = parts.hostname or "127.0.0.1"
        self.port = parts.port or (443 if parts.scheme == "https" else 80)
        self._process: subprocess.Popen[str] | None = None
        self._job: _Job | None = None
        self._output: collections.deque[str] = collections.deque(maxlen=OUTPUT_LINES)
        self._reader: threading.Thread | None = None

    @property
    def running(self) -> bool:
        """Whether the command is still running."""
        return self._process is not None and self._process.poll() is None

    @property
    def output_tail(self) -> str:
        """The last lines the command printed, which explain most failures."""
        return "\n".join(self._output)

    def start(self) -> None:
        """Run the command and return once its address answers."""
        if self._process is not None:
            raise RuntimeError("the command was already started")
        if _listening(self.host, self.port):
            raise RuntimeError(
                f"Something is already listening on {self.host}:{self.port}. Stop it, or show "
                "that address with Url instead of starting a second server."
            )
        self._launch()
        try:
            self._wait_until_ready()
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        """Stop the command and everything it started. Safe to call more than once."""
        process, job = self._process, self._job
        if process is None:
            return
        if job is not None:
            job.kill()
        if process.poll() is None:
            process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):  # a killed process ends at once
            process.wait(STOP_TIMEOUT)
        if self._reader is not None:
            self._reader.join(STOP_TIMEOUT)
        if process.stdout is not None:
            process.stdout.close()

    # ----- internals ------------------------------------------------------------------------

    def _launch(self) -> None:
        source = self.source
        options: dict[str, Any] = {
            "cwd": str(Path(source.cwd)) if source.cwd is not None else None,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if sys.platform == "win32":
            options["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        try:
            # The host chose this command, and a string is meant to run through the shell.
            self._process = subprocess.Popen(  # noqa: S603
                source.command, shell=isinstance(source.command, str), **options
            )
        except OSError as exc:
            raise RuntimeError(f"could not start {_describe(source.command)}: {exc}") from exc
        if sys.platform == "win32":
            self._job = _Job()
            self._job.add(self._process)
        self._reader = threading.Thread(target=self._drain, name="cornea-process", daemon=True)
        self._reader.start()

    def _drain(self) -> None:
        """Keep reading the command's output, so a full pipe never blocks it."""
        process = self._process
        assert process is not None  # noqa: S101
        assert process.stdout is not None  # noqa: S101
        try:
            for line in process.stdout:
                self._output.append(line.rstrip())
        except (OSError, ValueError):
            pass  # the pipe was closed while stopping

    def _wait_until_ready(self) -> None:
        process = self._process
        assert process is not None  # noqa: S101
        deadline = time.monotonic() + self.source.timeout
        while True:
            code = process.poll()
            if code is not None:
                raise RuntimeError(
                    f"{_describe(self.source.command)} exited with code {code} before "
                    f"{self.host}:{self.port} was ready.{self._tail()}"
                )
            if _listening(self.host, self.port):
                return
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"{self.host}:{self.port} did not answer within {self.source.timeout:g} "
                    f"seconds after starting {_describe(self.source.command)}.{self._tail()}"
                )
            time.sleep(POLL_INTERVAL)

    def _tail(self) -> str:
        tail = self.output_tail
        return f"\nIts last output:\n{tail}" if tail else ""


def _describe(command: str | tuple[str, ...]) -> str:
    return repr(command if isinstance(command, str) else " ".join(command))
