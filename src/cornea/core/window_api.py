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

from cornea.core.bridge import ActionRegistry, invoke_action
from cornea.core.window import WindowController


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
        _, payload = asyncio.run(
            invoke_action(self._actions, action, parameters or {}, self._controller)
        )
        return payload

    def _window(self) -> WindowController:
        if self._controller is None:
            raise RuntimeError("the window is not ready yet")
        return self._controller
