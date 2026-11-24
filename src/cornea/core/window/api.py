"""The object a page can call from JavaScript as ``window.pywebview.api``.

This is opt-in (``Window(js_api=True)``) and it is what lets a frameless window show an address
that Cornea does not serve: such a page cannot reach the HTTP routes, but pywebview puts this object
into whatever page the window shows.

Every public method here is callable by the page, and so is every public method of anything this
object holds, so the fields are private. Any page that loads in the window gets these powers,
including one it navigates to, so only use it for pages you trust.
"""

import asyncio
from typing import Any

from cornea.core.bridge.bridge import ActionRegistry
from cornea.core.window.window import (
    WindowController,
    check_coordinate,
    check_limit,
    check_side,
)


class WindowApi:
    """The window controls and the native actions, for a page to call."""

    def __init__(self, actions: ActionRegistry) -> None:
        self._actions = actions
        self._controller: WindowController | None = None

    def minimize(self) -> dict[str, bool]:
        """Minimize the window."""
        self._window().minimize()
        return {"ok": True}

    def maximize(self) -> dict[str, bool]:
        """Maximize the window."""
        self._window().maximize()
        return {"ok": True}

    def restore(self) -> dict[str, bool]:
        """Restore the window from maximized or minimized."""
        self._window().restore()
        return {"ok": True}

    def close(self, force: bool = False) -> dict[str, bool]:
        """Close the window. If the app holds it open this answers ``blocked`` unless ``force``."""
        if self._window().close(force=bool(force)):
            return {"ok": True}
        return {"ok": False, "blocked": True}

    def set_title(self, title: str) -> dict[str, bool]:
        """Change the window title."""
        if not isinstance(title, str) or not 1 <= len(title) <= 200:
            raise ValueError("title must be 1 to 200 characters")
        self._window().set_title(title)
        return {"ok": True}

    def set_always_on_top(self, enabled: bool) -> dict[str, bool]:
        """Keep the window above the others (or stop)."""
        self._window().set_always_on_top(bool(enabled))
        return {"ok": True}

    def set_fullscreen(self, enabled: bool) -> dict[str, bool]:
        """Fill the screen without a frame (or go back)."""
        self._window().set_fullscreen(bool(enabled))
        return {"ok": True}

    def set_size_limits(
        self, min_size: list[int] | None = None, max_size: list[int] | None = None
    ) -> dict[str, bool]:
        """Set the smallest and largest size, each ``[width, height]`` or ``None``."""
        self._window().set_size_limits(
            check_limit(min_size, "min_size"), check_limit(max_size, "max_size")
        )
        return {"ok": True}

    def bounds(self) -> dict[str, int | None]:
        """The window's ``x``, ``y``, ``width`` and ``height``."""
        return self._window().bounds()

    def set_position(self, x: int, y: int) -> dict[str, bool]:
        """Move the window's top-left corner."""
        self._window().set_bounds(x=check_coordinate(x, "x"), y=check_coordinate(y, "y"))
        return {"ok": True}

    def set_size(self, width: int, height: int) -> dict[str, bool]:
        """Resize the window."""
        self._window().set_bounds(
            width=check_side(width, "width"), height=check_side(height, "height")
        )
        return {"ok": True}

    def state(self) -> dict[str, Any]:
        """The title and whether the window is maximized, minimized, closed or frameless."""
        return self._window().state()

    def actions(self) -> list[str]:
        """The names of the native actions the page can call."""
        return self._actions.names()

    def call_action(self, action: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a native action. The answer has the same shape as the HTTP bridge route's.

        The second parameter is not called ``arguments`` on purpose: pywebview builds the
        JavaScript function from these names, and that word would hide JavaScript's own.
        """
        _, payload = asyncio.run(self._actions.invoke(action, parameters or {}, self._controller))
        return payload

    def _window(self) -> WindowController:
        if self._controller is None:
            raise RuntimeError("the window is not ready yet")
        return self._controller
