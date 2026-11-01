"""The native bridge: a short allowlist of native actions the page can call."""

import inspect
import logging
import os
import platform
import re
import subprocess
import sys
import webbrowser
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi.encoders import jsonable_encoder
from starlette.concurrency import run_in_threadpool

from cornea.core.page.notifications import Notifier
from cornea.core.window.window import Unavailable, WindowController

logger = logging.getLogger(__name__)
ACTION_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
OPEN_SCHEMES = frozenset({"http", "https", "mailto"})
MAX_URL_LENGTH = 2048


class BadArguments(ValueError):
    """The page called an action with arguments it cannot take."""


class UnknownAction(LookupError):
    """No such action, or it is switched off."""


SAFE_SUFFIXES = frozenset(
    {
        ".txt", ".md", ".csv", ".tsv", ".log", ".json", ".xml", ".yaml", ".yml", ".rtf",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico",
        ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".mp4", ".mkv", ".mov", ".avi", ".webm",
    }
)  # fmt: skip
"""The only types ``open_file`` opens: documents, images, audio and video. Anything else can run
code or load active content, so it is refused."""
MAX_PATH_LENGTH = 4096
OPT_IN_FILES = frozenset({"open_file", "reveal"})
"""Built-in actions that are off until ``Bridge(open_files=True)``."""
OPT_IN_NOTIFICATIONS = frozenset({"show_notification"})
"""Built-in actions that are off until ``Bridge(notifications=True)``."""


class BuiltinActions:
    """The actions that come with the bridge: each takes the window, then the page's arguments."""

    @staticmethod
    def choose_folder(window: WindowController | None, directory: str | None = None) -> Any:
        """Show a folder dialog. Returns the folder, or ``None`` when cancelled."""
        chosen = BuiltinActions._window(window).dialog("folder", directory=directory)
        return chosen[0] if chosen else None

    @staticmethod
    def choose_file(
        window: WindowController | None,
        directory: str | None = None,
        file_types: Sequence[str] = (),
        multiple: bool = False,
    ) -> Any:
        """Show an open dialog. Returns a list of files, or ``None`` when cancelled."""
        return BuiltinActions._window(window).dialog(
            "open", directory=directory, file_types=file_types, multiple=multiple
        )

    @staticmethod
    def save_file(
        window: WindowController | None,
        directory: str | None = None,
        filename: str | None = None,
        file_types: Sequence[str] = (),
    ) -> Any:
        """Show a save dialog. Returns the chosen path, or ``None``. Nothing is written."""
        chosen = BuiltinActions._window(window).dialog(
            "save", directory=directory, filename=filename, file_types=file_types
        )
        return chosen[0] if chosen else None

    @staticmethod
    def open_external(window: WindowController | None, url: str) -> Any:
        """Open an http, https or mailto address in the system's own program."""
        if not isinstance(url, str) or not url.strip():
            raise BadArguments("url must be a non-empty string")
        address = url.strip()
        if len(address) > MAX_URL_LENGTH or any(ord(char) < 32 for char in address):
            raise BadArguments("url is too long or contains control characters")
        if urlsplit(address).scheme.lower() not in OPEN_SCHEMES:
            raise BadArguments("only http, https and mailto addresses can be opened")
        return {"opened": bool(webbrowser.open(address))}

    @staticmethod
    def _windows() -> bool:
        return sys.platform == "win32"

    @staticmethod
    def _existing_path(path: object) -> Path:
        """The path as an absolute one, if it exists and is not on the network."""
        if not isinstance(path, str) or not path.strip() or "\0" in path:
            raise BadArguments("path must be a non-empty string")
        if len(path) > MAX_PATH_LENGTH:
            raise BadArguments("path is too long")
        if path.startswith(("\\\\", "//")):
            raise BadArguments("network paths cannot be opened")
        target = Path(path).resolve()
        if str(target).startswith("\\\\"):  # a link that leads to the network
            raise BadArguments("network paths cannot be opened")
        if not target.exists():
            raise BadArguments("that path does not exist")
        return target

    @staticmethod
    def open_file(window: WindowController | None, path: str) -> Any:
        """Open a file in the program Windows has for it: documents, images, audio and video."""
        target = BuiltinActions._existing_path(path)
        if target.is_dir():
            raise BadArguments("that is a folder; use reveal to show it")
        suffix = target.suffix.lower()
        if suffix not in SAFE_SUFFIXES:
            raise BadArguments("files of that type cannot be opened from a page")
        if not BuiltinActions._windows():
            raise Unavailable("Opening files only works on Windows for now.")
        os.startfile(target)  # noqa: S606 - the type was checked above
        return {"opened": True}

    @staticmethod
    def reveal(window: WindowController | None, path: str) -> Any:
        """Show a file or folder in Explorer, selecting a file."""
        target = BuiltinActions._existing_path(path)
        if not BuiltinActions._windows():
            raise Unavailable("Showing files only works on Windows for now.")
        arguments = (
            ["explorer", str(target)] if target.is_dir() else ["explorer", "/select,", str(target)]
        )
        subprocess.Popen(arguments)  # noqa: S603 - a fixed program with a checked path
        return {"shown": True}

    @staticmethod
    def show_notification(
        window: WindowController | None,
        title: str,
        message: str,
        notification_id: str | None = None,
    ) -> Any:
        """Show a Windows toast with a title and a plain-text message.

        A click brings the window to the front and sends the page a ``cornea:notification-click``
        event carrying ``notification_id``.
        """
        Notifier.check(title, message, notification_id)
        BuiltinActions._window(window, "a notification").show_notification(
            title, message, notification_id
        )
        return {"shown": True}

    @staticmethod
    def platform_info(window: WindowController | None) -> Any:
        """Describe the system, the Python in use and whether a window exists."""
        from cornea import __version__
        from cornea.core.window import window as window_module

        webview2 = None
        if sys.platform == "win32":
            webview2 = window_module._registry_version()
        return {
            "platform": platform.system().lower(),
            "release": platform.release(),
            "version": platform.version(),
            "python": platform.python_version(),
            "cornea": __version__,
            "webview2": webview2,
            "window": window is not None and not window.headless,
        }

    @staticmethod
    def _window(window: WindowController | None, what: str = "a dialog") -> WindowController:
        if window is None:
            raise Unavailable(f"There is no window to show {what} in.")
        return window

    @staticmethod
    def table() -> dict[str, Callable[..., Any]]:
        """The built-in actions by name."""
        return {
            "choose_folder": BuiltinActions.choose_folder,
            "choose_file": BuiltinActions.choose_file,
            "save_file": BuiltinActions.save_file,
            "open_external": BuiltinActions.open_external,
            "platform_info": BuiltinActions.platform_info,
            "open_file": BuiltinActions.open_file,
            "reveal": BuiltinActions.reveal,
            "show_notification": BuiltinActions.show_notification,
        }


BUILTINS: dict[str, Callable[..., Any]] = BuiltinActions.table()


class ActionRegistry:
    """The actions the page may call: the built-ins that are on, and the host's own.

    Example:
        >>> actions = ActionRegistry()
        >>> @actions.action("greet")
        ... def greet(name: str) -> str:
        ...     return f"Hello, {name}!"
        >>> "greet" in actions.names()
        True
    """

    def __init__(
        self,
        disabled: Iterable[str] = (),
        *,
        open_files: bool = False,
        notifications: bool = False,
    ) -> None:
        off = set(disabled)
        unknown = off - set(BUILTINS)
        if unknown:
            raise ValueError(f"cannot disable unknown built-in actions: {sorted(unknown)}")
        self._builtins = {
            name: fn
            for name, fn in BUILTINS.items()
            if name not in off
            and (open_files or name not in OPT_IN_FILES)
            and (notifications or name not in OPT_IN_NOTIFICATIONS)
        }
        self._custom: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, function: Callable[..., Any]) -> Callable[..., Any]:
        """Add the host's own action. Names are lowercase words joined by underscores."""
        if not ACTION_NAME.match(name):
            raise ValueError(f"action names look like 'pick_report', got {name!r}")
        if name in BUILTINS:
            raise ValueError(f"{name!r} is a built-in action and cannot be replaced")
        if name in self._custom:
            raise ValueError(f"action {name!r} is already registered")
        self._custom[name] = function
        return function

    def action(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a function as an action: ``@shell.action("name")``."""

        def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
            return self.register(name, function)

        return decorate

    def names(self) -> list[str]:
        """The actions the page can call, built-ins first."""
        return [*self._builtins, *self._custom]

    async def call(
        self, name: str, arguments: dict[str, Any], window: WindowController | None
    ) -> Any:
        """Run an action. Raises :class:`UnknownAction`, :class:`BadArguments` or what it raises."""
        if name in self._builtins:
            function: Callable[..., Any] = self._builtins[name]
            bound: tuple[Any, ...] = (window,)
        elif name in self._custom:
            function, bound = self._custom[name], ()
        else:
            raise UnknownAction(name)
        try:
            inspect.signature(function).bind(*bound, **arguments)
        except TypeError as exc:
            raise BadArguments(str(exc)) from exc
        if inspect.iscoroutinefunction(function):
            return await function(*bound, **arguments)
        return await run_in_threadpool(function, *bound, **arguments)

    async def invoke(
        self,
        name: str,
        arguments: dict[str, Any],
        window: WindowController | None,
    ) -> tuple[int, dict[str, Any]]:
        """Run an action and describe the outcome as an HTTP status and a JSON-ready body.

        A dialog that cannot be shown (no window) is ``available: false`` and not an error. A crash
        in an action is logged with its details but the caller only learns that it failed.
        """
        # The arguments and the result are never logged: they can hold paths and personal data.
        try:
            result = await self.call(name, arguments, window)
        except UnknownAction:
            logger.debug("Action %r: unknown or switched off", name)
            return 404, {"error": "Unknown action"}
        except BadArguments as exc:
            logger.debug("Action %r: bad arguments: %s", name, exc)
            return 422, {"error": str(exc)}
        except Unavailable as exc:
            logger.debug("Action %r: not available: %s", name, exc)
            return 200, {"available": False, "reason": str(exc)}
        except ValueError as exc:
            logger.debug("Action %r: rejected: %s", name, exc)
            return 422, {"error": str(exc)}
        except Exception:
            logger.exception("The action %r failed", name)
            return 500, {"error": "The action failed"}
        logger.debug("Action %r: done", name)
        return 200, {"available": True, "result": jsonable_encoder(result)}
