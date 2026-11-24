"""Register a custom URL scheme and file types for the current user.

``myapp://open/42`` links and registered files then start the app, with the address or the file's
path as an argument (see :class:`~cornea.core.app.launch.LaunchRequest`). With
``App(single_instance=True)`` a second start hands that argument to the running copy.

Everything is written under ``HKEY_CURRENT_USER\\Software\\Classes``, so no administrator rights
are needed and other users are not affected. File types are added to a type's "Open with" list and
never take over its default program: Windows keeps that choice with the person. Windows only.

Nothing is registered unless your code asks, and the page cannot ask.
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

CLASSES = r"Software\Classes"
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]{1,31}$")
EXTENSION = re.compile(r"^\.[a-z0-9_-]{1,16}$")
MAX_NAME = 128

RESERVED_SCHEMES = frozenset(
    {
        "http", "https", "file", "ftp", "ftps", "mailto", "tel", "sms", "data", "javascript",
        "about", "blob", "ws", "wss", "ldap", "news", "nntp", "telnet", "ssh", "sftp", "vbscript",
        "ms-settings", "ms-windows-store", "search-ms", "shell", "cmd", "powershell",
    }
)  # fmt: skip
"""Schemes Windows or browsers already own. Taking one over would break links everywhere."""
DANGEROUS_EXTENSIONS = frozenset(
    {
        ".exe", ".com", ".scr", ".pif", ".bat", ".cmd", ".msi", ".msp", ".ps1", ".psm1", ".vbs",
        ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta", ".lnk", ".url", ".reg", ".dll", ".sys",
        ".jar", ".cpl", ".msc", ".inf", ".gadget", ".appx", ".msix", ".library-ms",
        ".settingcontent-ms",
    }
)  # fmt: skip
"""Types that run code or change the system. An app cannot claim them."""


class Associations:
    """The URL scheme and file types one app registers for the current user.

    Example:
        >>> Associations("com.example.notes").app_id
        'com.example.notes'
        >>> Associations.check_scheme("MyApp")
        'myapp'
    """

    def __init__(self, app_id: str) -> None:
        self.app_id = app_id

    # ----- checks ----------------------------------------------------------------------------

    @staticmethod
    def check_scheme(scheme: object) -> str:
        """The scheme in lowercase, or an error if it cannot be registered.

        Raises:
            ValueError: With what is wrong.
        """
        if not isinstance(scheme, str) or not SCHEME.match(scheme.strip().lower()):
            raise ValueError(
                "a scheme is 2 to 32 letters, digits, '+', '-' or '.', starting with a letter"
            )
        name = scheme.strip().lower()
        if name in RESERVED_SCHEMES:
            raise ValueError(f"{name!r} belongs to the system and cannot be registered")
        return name

    @staticmethod
    def check_extension(extension: object) -> str:
        """The extension in lowercase with its dot, or an error if it cannot be registered.

        Raises:
            ValueError: With what is wrong.
        """
        if not isinstance(extension, str):
            raise ValueError("an extension looks like '.notes'")
        name = extension.strip().lower()
        if not name.startswith("."):
            name = "." + name
        if not EXTENSION.match(name):
            raise ValueError("an extension looks like '.notes': letters, digits, '_' or '-'")
        if name in DANGEROUS_EXTENSIONS:
            raise ValueError(f"{name!r} files run code or change the system and cannot be claimed")
        return name

    @staticmethod
    def _check_text(label: str, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be a non-empty string")
        if len(value) > MAX_NAME or any(ord(char) < 32 for char in value):
            raise ValueError(f"{label} is too long or has control characters")
        return value.strip()

    @staticmethod
    def default_command() -> str:
        """The command that starts this program, without the argument.

        A packaged program starts as itself. A Python script starts with ``pythonw.exe`` when it
        is next to the interpreter, so no console window appears.
        """
        if getattr(sys, "frozen", False):
            return subprocess.list2cmdline([sys.executable])
        executable = Path(sys.executable)
        windowless = executable.with_name("pythonw.exe")
        program = windowless if windowless.exists() else executable
        script = [str(Path(sys.argv[0]).resolve())] if sys.argv and sys.argv[0] else []
        return subprocess.list2cmdline([str(program), *script])

    @staticmethod
    def _open_command(command: str | None) -> str:
        base = Associations._check_text("command", command) if command else None
        # "%1" is always quoted: it is text from outside and must stay one argument.
        return f'{base or Associations.default_command()} "%1"'

    # ----- URL scheme ------------------------------------------------------------------------

    def register_protocol(
        self, scheme: str, *, command: str | None = None, name: str | None = None
    ) -> str:
        """Make ``scheme://...`` links start the app. Returns the scheme.

        ``command`` replaces the program to start (the address is added after it) and ``name`` is
        the description Windows shows. Registering again replaces the entry.

        Raises:
            ValueError: If the scheme is not allowed (it needs 2 or more characters and must not
                be one Windows or browsers own) or the command or name is not usable.
            RuntimeError: If this is not Windows.
        """
        key = Associations.check_scheme(scheme)
        label = Associations._check_text("name", name) if name else f"{self.app_id} link"
        launch = Associations._open_command(command)
        winreg = self._winreg()
        base = f"{CLASSES}\\{key}"
        self._set(winreg, base, None, f"URL:{label}")
        self._set(winreg, base, "URL Protocol", "")
        self._set(winreg, base, "CorneaApp", self.app_id)
        self._set(winreg, f"{base}\\shell\\open\\command", None, launch)
        return key

    def unregister_protocol(self, scheme: str) -> bool:
        """Remove a scheme this app registered. Returns whether there was one to remove.

        A scheme registered by another program is left alone.
        """
        key = Associations.check_scheme(scheme)
        winreg = self._winreg()
        path = f"{CLASSES}\\{key}"
        if not self._owned(winreg, path):
            return False
        return self._delete_tree(winreg, path)

    def protocol_command(self, scheme: str) -> str | None:
        """The command registered for ``scheme``, or ``None`` when there is none."""
        key = Associations.check_scheme(scheme)
        return self._get(self._winreg(), f"{CLASSES}\\{key}\\shell\\open\\command", None)

    # ----- file types ------------------------------------------------------------------------

    def register_file_type(
        self,
        extension: str,
        *,
        description: str | None = None,
        command: str | None = None,
    ) -> str:
        """Add the app to the "Open with" list of ``extension``. Returns the extension.

        The app is not made the default program: Windows leaves that to the person. ``command``
        replaces the program to start (the file's path is added after it).

        Raises:
            ValueError: If the extension is not allowed (programs and scripts cannot be claimed)
                or the command or description is not usable.
            RuntimeError: If this is not Windows.
        """
        ext = Associations.check_extension(extension)
        label = (
            Associations._check_text("description", description)
            if description
            else f"{ext[1:].upper()} file"
        )
        launch = Associations._open_command(command)
        winreg = self._winreg()
        prog_id = self._prog_id(ext)
        self._set(winreg, f"{CLASSES}\\{prog_id}", None, label)
        self._set(winreg, f"{CLASSES}\\{prog_id}", "CorneaApp", self.app_id)
        self._set(winreg, f"{CLASSES}\\{prog_id}\\shell\\open\\command", None, launch)
        self._set(winreg, f"{CLASSES}\\{ext}\\OpenWithProgids", prog_id, "")
        return ext

    def unregister_file_type(self, extension: str) -> bool:
        """Remove this app from the "Open with" list of ``extension``.

        Returns whether there was an entry to remove.
        """
        ext = Associations.check_extension(extension)
        winreg = self._winreg()
        prog_id = self._prog_id(ext)
        removed = self._delete_value(winreg, f"{CLASSES}\\{ext}\\OpenWithProgids", prog_id)
        path = f"{CLASSES}\\{prog_id}"
        if self._owned(winreg, path):
            removed = self._delete_tree(winreg, path) or removed
        return removed

    def file_type_command(self, extension: str) -> str | None:
        """The command registered for ``extension``, or ``None`` when there is none."""
        ext = Associations.check_extension(extension)
        prog_id = self._prog_id(ext)
        return self._get(self._winreg(), f"{CLASSES}\\{prog_id}\\shell\\open\\command", None)

    def _prog_id(self, ext: str) -> str:
        return f"{self.app_id}{ext}"

    # ----- the registry ----------------------------------------------------------------------

    def _owned(self, winreg: Any, path: str) -> bool:
        """Whether this app made the entry: it marks what it registers with its id."""
        return self._get(winreg, path, "CorneaApp") == self.app_id

    @staticmethod
    def _set(winreg: Any, path: str, name: str | None, value: str) -> None:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name or "", 0, winreg.REG_SZ, value)

    @staticmethod
    def _get(winreg: Any, path: str, name: str | None) -> str | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as key:
                return str(winreg.QueryValueEx(key, name or "")[0])
        except FileNotFoundError:
            return None

    @staticmethod
    def _delete_value(winreg: Any, path: str, name: str) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            return False
        return True

    @staticmethod
    def _delete_tree(winreg: Any, path: str) -> bool:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE
            ) as key:
                children = []
                index = 0
                while True:
                    try:
                        children.append(winreg.EnumKey(key, index))
                    except OSError:
                        break
                    index += 1
        except FileNotFoundError:
            return False
        for child in children:
            Associations._delete_tree(winreg, f"{path}\\{child}")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        return True

    @staticmethod
    def _winreg() -> Any:
        if sys.platform != "win32":
            raise RuntimeError("Protocols and file types only work on Windows for now.")
        import winreg

        return winreg
