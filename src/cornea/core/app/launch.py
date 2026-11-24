"""What an app was started with: its arguments, and which of them are addresses or files.

When a person opens ``myapp://open/42`` or double-clicks a registered file, Windows starts the
program with that text as an argument. With ``single_instance`` the new copy hands its request to
the copy that is already running and exits. Both end up as a :class:`LaunchRequest`.

The arguments come from outside the app (a web page can open ``myapp://`` links, and a file name
is chosen by whoever made the file), so treat every part of one as untrusted input.
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_ARGS = 64
MAX_ARG = 4096
_URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]{1,31}://")


@dataclass(frozen=True, slots=True)
class LaunchRequest:
    """The arguments a copy of the app was started with.

    Example:
        >>> request = LaunchRequest.from_args(["myapp://open/42", "--flag"])
        >>> request.urls
        ('myapp://open/42',)
        >>> request.args
        ('myapp://open/42', '--flag')
    """

    args: tuple[str, ...] = ()
    """Every argument after the program, as given. Files are made absolute."""
    urls: tuple[str, ...] = field(default=())
    """The arguments that look like ``scheme://...`` addresses."""
    files: tuple[str, ...] = field(default=())
    """The arguments that name an existing file, as absolute paths."""

    @staticmethod
    def from_args(args: list[str] | tuple[str, ...] | None = None) -> "LaunchRequest":
        """Read ``args`` (default: this program's own arguments).

        A name that exists on disk becomes an absolute path, using the folder this copy was
        started in, so another copy can use it.

        Raises:
            ValueError: If there are too many arguments or one is too long or has a null character.
        """
        given = list(sys.argv[1:] if args is None else args)
        LaunchRequest._check(given)
        resolved: list[str] = []
        urls: list[str] = []
        files: list[str] = []
        for arg in given:
            if _URL.match(arg):
                urls.append(arg)
                resolved.append(arg)
            elif LaunchRequest._is_file(arg):
                absolute = str(Path(arg).resolve())
                files.append(absolute)
                resolved.append(absolute)
            else:
                resolved.append(arg)
        return LaunchRequest(tuple(resolved), tuple(urls), tuple(files))

    @staticmethod
    def from_json(data: Any) -> "LaunchRequest":
        """Rebuild a request sent by another copy, checking every part.

        Raises:
            ValueError: If it is not what :meth:`as_json` produces.
        """
        if not isinstance(data, dict):
            raise ValueError("a launch request is an object")
        parts: list[tuple[str, ...]] = []
        for name in ("args", "urls", "files"):
            value = data.get(name, [])
            if not isinstance(value, list):
                raise ValueError(f"{name} must be a list")
            LaunchRequest._check(value)
            parts.append(tuple(value))
        return LaunchRequest(*parts)

    def as_json(self) -> dict[str, list[str]]:
        """The request as JSON, which is also the detail of the page's ``cornea:launch`` event."""
        return {"args": list(self.args), "urls": list(self.urls), "files": list(self.files)}

    @staticmethod
    def _check(values: list[Any]) -> None:
        if len(values) > MAX_ARGS:
            raise ValueError(f"at most {MAX_ARGS} arguments are allowed")
        for value in values:
            if not isinstance(value, str) or len(value) > MAX_ARG or "\0" in value:
                raise ValueError("arguments must be short strings without null characters")

    @staticmethod
    def _is_file(arg: str) -> bool:
        try:
            return bool(arg) and not arg.startswith("-") and Path(arg).is_file()
        except OSError:
            return False
