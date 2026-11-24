"""The menus of one shell: what is defined, what a click does, and the routes the page uses."""

import inspect
import logging
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cornea_menus.model import (
    THEMES,
    ContextMenu,
    MenuBar,
    MenuError,
    Mode,
    Node,
    Theme,
    check_context_name,
    normalise,
    to_node,
)

if TYPE_CHECKING:
    from fastapi import APIRouter

    from cornea.core.shell import Shell

logger = logging.getLogger(__name__)

MAX_PAGE_BYTES = 262_144
"""The most a page may send as a menu definition."""


@dataclass(frozen=True, slots=True)
class MenuClick:
    """What a handler is told when an entry is chosen."""

    id: str
    """The entry's ``id``."""
    checked: bool | None
    """For a check or radio entry, whether it is on now. ``None`` for the others."""
    menu: str | None
    """The context menu it was chosen in, or ``None`` for the menu bar."""


Handler = Callable[..., Any]


def _find(entries: list[Node], ident: str) -> tuple[list[Node], Node] | None:
    for entry in entries:
        if entry.get("id") == ident:
            return entries, entry
        found = _find(entry["items"], ident) if entry["type"] == "submenu" else None
        if found is not None:
            return found
    return None


class Menus:
    """The menus a shell shows, and the extension that adds them to it.

    ``Shell(..., extensions=[menus])`` mounts the routes, serves the script and styles from
    ``{api_prefix}/menus``, and, in frame mode, opens the window on a page that draws the title
    bar and menu bar around your app.

    Args:
        bar: The menus along the top, or ``None`` for none.
        context: Context menus, by name.
        theme: ``win11``, ``xp``, ``office``, ``macos`` or ``ubuntu``.
        mode: ``component``: your page mounts the bar itself (``cornea.menus.mount``). ``frame``:
            Cornea draws the bars and shows your app in a frame below them, with no change to the
            app.
        app_path: Frame mode only. The address of your app, shown in the frame.
        page_can_define: Let the page define menus itself with ``cornea.menus.set``. A page can
            only show entries and hear clicks that way; Python handlers run only for entries
            Python knows.

    Example:
        >>> menus = Menus(theme="xp")
        >>> menus.theme
        'xp'
    """

    def __init__(
        self,
        bar: MenuBar | Iterable[Any] | None = None,
        context: Iterable[ContextMenu] | Mapping[str, Iterable[Any]] | None = None,
        *,
        theme: Theme = "win11",
        mode: Mode = "component",
        app_path: str = "/",
        page_can_define: bool = True,
    ) -> None:
        if theme not in THEMES:
            raise ValueError(f"theme must be one of {', '.join(THEMES)}, got {theme!r}")
        if mode not in ("component", "frame"):
            raise ValueError(f"mode must be 'component' or 'frame', got {mode!r}")
        if not app_path.startswith("/") or app_path.startswith("//") or "\\" in app_path:
            raise ValueError(
                f"app_path must be an address on this app such as '/', got {app_path!r}"
            )
        self.theme: Theme = theme
        self.mode: Mode = mode
        self.app_path = app_path
        self.page_can_define = page_can_define
        self._lock = threading.RLock()
        self._version = 0
        self._bar: list[Node] = []
        self._context: dict[str, list[Node]] = {}
        self._handlers: dict[str, list[Handler]] = {}
        self._any: list[Handler] = []
        self._shell: Shell | None = None
        self._router: APIRouter | None = None
        if bar is not None or context is not None:
            self.define(bar, context)

    # ----- Extension --------------------------------------------------------------------------

    @property
    def allows_framing(self) -> bool:
        """Frame mode shows the app in a frame, so the page must be allowed to frame itself."""
        return self.mode == "frame"

    def routers(self) -> Iterable["APIRouter"]:
        from cornea_menus.routes import build_router

        if self._router is None:
            self._router = build_router(self)
        return [self._router]

    def start_path(self, api_prefix: str) -> str:
        return f"{api_prefix}/menus/frame" if self.mode == "frame" else "/"

    def bind(self, shell: "Shell") -> None:
        self._shell = shell

    # ----- defining ---------------------------------------------------------------------------

    def define(
        self,
        bar: MenuBar | Iterable[Any] | None = None,
        context: Iterable[ContextMenu] | Mapping[str, Iterable[Any]] | None = None,
    ) -> None:
        """Replace the whole definition. Nothing changes if any part is not allowed.

        Raises:
            MenuError: If an entry is not allowed or an id is used twice.

        Example:
            >>> from cornea_menus import Item, ContextMenu
            >>> menus = Menus()
            >>> menus.define(context=[ContextMenu("default", [Item("edit.copy", "Copy")])])
            >>> list(menus.definition()["context"])
            ['default']
        """
        used: set[str] = set()
        bar_nodes = normalise(
            bar.to_nodes() if isinstance(bar, MenuBar) else (bar or []), bar=True, used=used
        )
        pairs: list[tuple[str, Iterable[Any]]]
        if context is None:
            pairs = []
        elif isinstance(context, Mapping):
            pairs = list(context.items())
        else:
            pairs = [(menu.name, menu.items) for menu in context]
        if len(pairs) > 50:
            raise MenuError("there may be at most 50 context menus")
        context_nodes = {
            check_context_name(name): normalise(items, used=used) for name, items in pairs
        }
        with self._lock:
            self._bar, self._context = bar_nodes, context_nodes
        self._changed()

    def set_bar(self, bar: MenuBar | Iterable[Any] | None) -> None:
        """Replace the menu bar and keep the context menus."""
        with self._lock:
            context = {name: list(items) for name, items in self._context.items()}
        self.define(bar, context)

    def set_context(self, name: str, items: Iterable[Any] | ContextMenu | None) -> None:
        """Add or replace one context menu, or remove it with ``None``."""
        with self._lock:
            bar = list(self._bar)
            context: dict[str, Iterable[Any]] = {n: list(v) for n, v in self._context.items()}
        if items is None:
            context.pop(name, None)
        else:
            context[name] = items.items if isinstance(items, ContextMenu) else items
        self.define(bar, context)

    def definition(self) -> dict[str, Any]:
        """Everything the page needs to draw the menus."""
        with self._lock:
            return {
                "version": self._version,
                "theme": self.theme,
                "mode": self.mode,
                "app_path": self.app_path,
                "page_can_define": self.page_can_define,
                "bar": self._bar,
                "context": self._context,
            }

    # ----- changing at run time ---------------------------------------------------------------

    def update(
        self,
        ident: str,
        *,
        label: str | None = None,
        enabled: bool | None = None,
        visible: bool | None = None,
        checked: bool | None = None,
        shortcut: str | None = None,
    ) -> None:
        """Change one entry while the app runs, and tell the page.

        Raises:
            KeyError: If there is no entry with that id.
            MenuError: If a value is not allowed, or ``checked`` is given for an entry without one.

        Example:
            >>> from cornea_menus import Item, Menu
            >>> menus = Menus([Menu("&File", [Item("file.save", "&Save")])])
            >>> menus.update("file.save", enabled=False)
            >>> menus.entry("file.save")["enabled"]
            False
        """
        changes = {
            "label": label,
            "enabled": enabled,
            "visible": visible,
            "checked": checked,
            "shortcut": shortcut,
        }
        with self._lock:
            found = self._locate(ident)
            if found is None:
                raise KeyError(ident)
            siblings, node = found
            candidate = {**node, **{k: v for k, v in changes.items() if v is not None}}
            if "checked" in changes and changes["checked"] is not None and "checked" not in node:
                raise MenuError(f"{ident!r} is not a check or radio entry")
            if node["type"] == "submenu":
                candidate["items"] = []  # checked below without descending
            checked_node = normalise([candidate], bar=False, used=set())[0]
            if node["type"] == "submenu":
                checked_node["items"] = node["items"]
            node.update({k: v for k, v in checked_node.items() if k != "type"})
            if node["type"] == "radio" and checked:
                self._select_radio(siblings, node)
        self._changed()

    def entry(self, ident: str) -> dict[str, Any]:
        """A copy of one entry as the page sees it.

        Raises:
            KeyError: If there is no entry with that id.
        """
        with self._lock:
            found = self._locate(ident)
            if found is None:
                raise KeyError(ident)
            return dict(found[1])

    def _locate(self, ident: str) -> tuple[list[Node], Node] | None:
        found = _find(self._bar, ident)
        if found is not None:
            return found
        for items in self._context.values():
            found = _find(items, ident)
            if found is not None:
                return found
        return None

    @staticmethod
    def _select_radio(siblings: list[Node], chosen: Node) -> None:
        for entry in siblings:
            if entry["type"] == "radio" and entry["group"] == chosen["group"]:
                entry["checked"] = entry is chosen

    # ----- handling clicks --------------------------------------------------------------------

    def on(self, ident: str) -> Callable[[Handler], Handler]:
        """Run a function when an entry is chosen: ``@menus.on("file.quit")``.

        The function takes no arguments, or one :class:`MenuClick`.

        Example:
            >>> menus = Menus()
            >>> @menus.on("file.quit")
            ... def quit_app() -> None:
            ...     pass
        """

        def register(function: Handler) -> Handler:
            self._handlers.setdefault(ident, []).append(function)
            return function

        return register

    def on_click(self, function: Handler) -> Handler:
        """Run a function for every entry that is chosen: ``@menus.on_click``."""
        self._any.append(function)
        return function

    def click(self, ident: str, menu: str | None = None) -> dict[str, Any]:
        """Choose an entry as the page does. Used by the click route.

        A check entry flips, a radio entry turns on and the others in its group turn off. The
        handlers run after the state has changed.

        Raises:
            KeyError: If the entry does not exist, is not in ``menu``, or cannot be chosen now
                (disabled or hidden).
        """
        with self._lock:
            found = self._locate_in(ident, menu)
            if found is None:
                raise KeyError(ident)
            siblings, node = found
            if (
                node["type"] in ("submenu", "separator")
                or not node["enabled"]
                or not node["visible"]
            ):
                raise KeyError(ident)
            checked: bool | None = None
            if node["type"] == "check":
                node["checked"] = not node["checked"]
                checked = node["checked"]
            elif node["type"] == "radio":
                self._select_radio(siblings, node)
                checked = True
            changed = checked is not None
        if changed:
            self._changed()
        click = MenuClick(ident, checked, menu)
        for handler in [*self._handlers.get(ident, ()), *self._any]:
            self._call(handler, click)
        return {"ok": True, "id": ident, "checked": checked, "menu": menu}

    def _locate_in(self, ident: str, menu: str | None) -> tuple[list[Node], Node] | None:
        if menu is None:
            return _find(self._bar, ident)
        items = self._context.get(menu)
        return None if items is None else _find(items, ident)

    @staticmethod
    def _call(handler: Handler, click: MenuClick) -> None:
        try:
            takes = len(inspect.signature(handler).parameters)
            if takes:
                handler(click)
            else:
                handler()
        except Exception:
            # What went wrong stays in the log; the page is only told the click was handled.
            logger.exception("The handler for the menu entry %r failed", click.id)

    # ----- the page ---------------------------------------------------------------------------

    def define_from_page(self, raw: Any) -> None:
        """Replace the definition with one the page sent.

        Raises:
            PermissionError: If ``page_can_define`` is off.
            MenuError: If anything is not allowed.
        """
        if not self.page_can_define:
            raise PermissionError("this app does not let the page define menus")
        if not isinstance(raw, Mapping):
            raise MenuError("send an object with 'bar' and 'context'")
        bar, context = raw.get("bar", []), raw.get("context", {})
        if not isinstance(bar, list | tuple) or not isinstance(context, Mapping):
            raise MenuError("'bar' must be a list and 'context' an object of lists")
        for name, items in context.items():
            if not isinstance(items, list | tuple):
                raise MenuError(f"the context menu {name!r} must be a list")
        self.define(list(bar), {str(n): [to_node(e) for e in v] for n, v in context.items()})

    def _changed(self) -> None:
        with self._lock:
            self._version += 1
            version = self._version
        shell = self._shell
        if shell is not None:
            shell.notify("menu-changed", {"version": version})
