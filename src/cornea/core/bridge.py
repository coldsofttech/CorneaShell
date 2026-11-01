"""The native bridge: a short allowlist of native actions the page can call."""

import inspect
import logging
import platform
import re
import sys
import webbrowser
from collections.abc import Callable, Iterable, Sequence
from typing import Any
from urllib.parse import urlsplit

from fastapi.encoders import jsonable_encoder
from starlette.concurrency import run_in_threadpool

from cornea.core.window import Unavailable, WindowController

logger = logging.getLogger(__name__)
ACTION_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
OPEN_SCHEMES = frozenset({"http", "https", "mailto"})
MAX_URL_LENGTH = 2048


class BadArguments(ValueError):
    """The page called an action with arguments it cannot take."""


class UnknownAction(LookupError):
    """No such action, or it is switched off."""


# ----- the built-in actions -------------------------------------------------------------------


def choose_folder(window: WindowController | None, directory: str | None = None) -> Any:
    """Show a folder dialog. Returns the folder, or ``None`` when cancelled."""
    chosen = _window(window).dialog("folder", directory=directory)
    return chosen[0] if chosen else None


def choose_file(
    window: WindowController | None,
    directory: str | None = None,
    file_types: Sequence[str] = (),
    multiple: bool = False,
) -> Any:
    """Show an open dialog. Returns a list of files, or ``None`` when cancelled."""
    return _window(window).dialog(
        "open", directory=directory, file_types=file_types, multiple=multiple
    )


def save_file(
    window: WindowController | None,
    directory: str | None = None,
    filename: str | None = None,
    file_types: Sequence[str] = (),
) -> Any:
    """Show a save dialog. Returns the chosen path, or ``None``. Nothing is written."""
    chosen = _window(window).dialog(
        "save", directory=directory, filename=filename, file_types=file_types
    )
    return chosen[0] if chosen else None


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


def platform_info(window: WindowController | None) -> Any:
    """Describe the system, the Python in use and whether a window exists."""
    from cornea import __version__
    from cornea.core import window as window_module

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


BUILTINS: dict[str, Callable[..., Any]] = {
    "choose_folder": choose_folder,
    "choose_file": choose_file,
    "save_file": save_file,
    "open_external": open_external,
    "platform_info": platform_info,
}


def _window(window: WindowController | None) -> WindowController:
    if window is None:
        raise Unavailable("There is no window to show a dialog in.")
    return window


async def invoke_action(
    registry: "ActionRegistry",
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
        result = await registry.call(name, arguments, window)
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


# ----- the registry ---------------------------------------------------------------------------


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

    def __init__(self, disabled: Iterable[str] = ()) -> None:
        off = set(disabled)
        unknown = off - set(BUILTINS)
        if unknown:
            raise ValueError(f"cannot disable unknown built-in actions: {sorted(unknown)}")
        self._builtins = {name: fn for name, fn in BUILTINS.items() if name not in off}
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
