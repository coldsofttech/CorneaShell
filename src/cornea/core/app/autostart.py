"""Start an app when its user logs in.

The app is registered for the current user only, under
``HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``. No administrator rights
are needed and other users are not affected. The entry is named after the app's id
(``App(id=...)``) and holds the command that starts the app, so it can be removed or checked
later. Windows only.

Nothing is registered unless your code asks: the page cannot turn autostart on.
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
MAX_COMMAND = 2048


@dataclass(frozen=True, slots=True)
class AutostartStatus:
    """Whether the app starts at login, and with which command.

    Example:
        >>> AutostartStatus(enabled=False).command is None
        True
    """

    enabled: bool
    """Whether an entry for this app exists."""
    command: str | None = None
    """The command stored in the entry, or ``None`` when there is none."""
    current: bool = False
    """Whether the stored command is the one this process would register now. ``False`` for an
    enabled app means the entry points somewhere else, for example at a moved program."""


class Autostart:
    """The start-at-login entry of one app.

    Example:
        >>> Autostart("com.example.notes").app_id
        'com.example.notes'
    """

    def __init__(self, app_id: str) -> None:
        self.app_id = app_id

    @staticmethod
    def default_command() -> str:
        """The command that starts this program the way it was started now.

        A packaged program starts as itself. A Python script starts with ``pythonw.exe`` when it
        is next to the interpreter, so no console window appears at login. Arguments are kept.
        """
        arguments = [str(Path(sys.argv[0]).resolve()), *sys.argv[1:]] if sys.argv[0] else []
        if getattr(sys, "frozen", False):
            return subprocess.list2cmdline([sys.executable, *sys.argv[1:]])
        executable = Path(sys.executable)
        windowless = executable.with_name("pythonw.exe")
        program = windowless if windowless.exists() else executable
        return subprocess.list2cmdline([str(program), *arguments])

    @staticmethod
    def check(command: object) -> str:
        """Refuse a command that cannot be stored safely.

        Raises:
            ValueError: With what is wrong.
        """
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command must be a non-empty string")
        if len(command) > MAX_COMMAND:
            raise ValueError(f"command can have at most {MAX_COMMAND} characters")
        if any(ord(char) < 32 for char in command):
            raise ValueError("command must not contain control characters")
        return command.strip()

    def enable(self, command: str | None = None) -> AutostartStatus:
        """Start the app at login. ``command`` defaults to :meth:`default_command`.

        Calling it again replaces the entry, so it also repairs one that points elsewhere.

        Raises:
            ValueError: If the command is not allowed.
            RuntimeError: If this is not Windows.
        """
        stored = Autostart.check(command) if command is not None else Autostart.default_command()
        winreg = self._winreg()
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, self.app_id, 0, winreg.REG_SZ, stored)
        return self.status()

    def disable(self) -> bool:
        """Stop starting the app at login. Returns whether there was an entry to remove."""
        winreg = self._winreg()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self.app_id)
        except FileNotFoundError:
            return False
        return True

    def status(self) -> AutostartStatus:
        """Whether the app starts at login now."""
        winreg = self._winreg()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, self.app_id)
        except FileNotFoundError:
            return AutostartStatus(enabled=False)
        command = str(value)
        return AutostartStatus(
            enabled=True, command=command, current=command == Autostart.default_command()
        )

    @property
    def enabled(self) -> bool:
        """Whether the app starts at login now."""
        return self.status().enabled

    @staticmethod
    def _winreg() -> Any:
        if sys.platform != "win32":
            raise RuntimeError("Starting at login only works on Windows for now.")
        import winreg

        return winreg
