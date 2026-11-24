"""Menu entries and their checks.

Python builds entries with the small classes below; a page sends the same shape as JSON. Both go
through :func:`normalise`, so a menu is checked the same way wherever it came from. A normalised
entry is a plain ``dict`` ready for JSON.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

MAX_DEPTH = 4
"""Deepest nesting of submenus, the top-level menu included."""
MAX_ENTRIES = 500
"""Most entries (separators included) in one menu bar or context menu."""
MAX_LABEL = 80
MAX_SHORTCUT = 32
MAX_CONTEXT_MENUS = 50

ID = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,63}$")
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
ICON = re.compile(r"^/[A-Za-z0-9._~/-]{1,200}$")
"""An icon is an address on the app's own server, for example ``/icons/save.svg``."""
SHORTCUT = re.compile(r"^[A-Za-z0-9+,.;/=\[\]\\'` -]{1,32}$")

Node = dict[str, Any]


class MenuError(ValueError):
    """The menu is not allowed. The message says which entry and why."""


@dataclass(frozen=True, slots=True)
class Item:
    """A menu entry that does something when chosen.

    Example:
        >>> Item("file.open", "&Open...", shortcut="Ctrl+O").id
        'file.open'
    """

    id: str
    label: str
    shortcut: str | None = None
    """Shown on the right, and pressed anywhere in the page: ``Ctrl+O``, ``F5``."""
    icon: str | None = None
    enabled: bool = True
    visible: bool = True

    def to_node(self) -> Node:
        return _entry("item", self)


@dataclass(frozen=True, slots=True)
class Check:
    """An entry that is on or off, with a tick."""

    id: str
    label: str
    checked: bool = False
    shortcut: str | None = None
    icon: str | None = None
    enabled: bool = True
    visible: bool = True

    def to_node(self) -> Node:
        return _entry("check", self)


@dataclass(frozen=True, slots=True)
class Radio:
    """One of several entries of which only one is on. Entries sharing ``group`` belong together."""

    id: str
    label: str
    group: str
    checked: bool = False
    shortcut: str | None = None
    icon: str | None = None
    enabled: bool = True
    visible: bool = True

    def to_node(self) -> Node:
        return _entry("radio", self)


@dataclass(frozen=True, slots=True)
class Separator:
    """A line between groups of entries."""

    def to_node(self) -> Node:
        return {"type": "separator"}


@dataclass(frozen=True, slots=True)
class Submenu:
    """An entry that opens another menu. A top-level menu of the bar is a ``Submenu`` too.

    Put ``&`` before the letter that opens it with Alt: ``Submenu("&File", [...])``.

    Example:
        >>> Submenu("&File", [Item("file.new", "&New")]).label
        '&File'
    """

    label: str
    items: tuple[Any, ...] | list[Any] = field(default_factory=tuple)
    id: str | None = None
    icon: str | None = None
    enabled: bool = True
    visible: bool = True

    def to_node(self) -> Node:
        node = _entry("submenu", self)
        node["items"] = [to_node(entry) for entry in self.items]
        return node


Menu = Submenu
"""Reads better for the top level of a bar: ``MenuBar([Menu("&File", [...])])``."""

Entry = Item | Check | Radio | Separator | Submenu


def _entry(kind: str, entry: Any) -> Node:
    node: Node = {"type": kind}
    for name in (
        "id",
        "label",
        "group",
        "checked",
        "shortcut",
        "icon",
        "enabled",
        "visible",
    ):
        if hasattr(entry, name):
            node[name] = getattr(entry, name)
    return node


def to_node(entry: Any) -> Node:
    """An entry class, or an entry that is already a mapping, as the plain form."""
    if isinstance(entry, Mapping):
        return dict(entry)
    to = getattr(entry, "to_node", None)
    if to is None:
        raise MenuError(f"not a menu entry: {entry!r}")
    node: Node = to()
    return node


# ----- checking ---------------------------------------------------------------------------------

_KINDS = {"item", "check", "radio", "separator", "submenu"}
_ALLOWED: dict[str, frozenset[str]] = {
    "item": frozenset({"type", "id", "label", "shortcut", "icon", "enabled", "visible"}),
    "check": frozenset(
        {"type", "id", "label", "checked", "shortcut", "icon", "enabled", "visible"}
    ),
    "radio": frozenset(
        {"type", "id", "label", "group", "checked", "shortcut", "icon", "enabled", "visible"}
    ),
    "separator": frozenset({"type"}),
    "submenu": frozenset({"type", "id", "label", "icon", "enabled", "visible", "items"}),
}


class _Walk:
    """What is counted while a menu is checked: entries seen and ids used."""

    def __init__(self, used: set[str]) -> None:
        self.entries = 0
        self.used = used


def _text(node: Mapping[str, Any], key: str, limit: int, where: str) -> str:
    value = node.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MenuError(f"{where}: {key} must be non-empty text")
    if len(value) > limit:
        raise MenuError(f"{where}: {key} is longer than {limit} characters")
    if any(ord(char) < 32 for char in value):
        raise MenuError(f"{where}: {key} must not contain control characters")
    return value


def _flag(node: Mapping[str, Any], key: str, default: bool, where: str) -> bool:
    value = node.get(key, default)
    if not isinstance(value, bool):
        raise MenuError(f"{where}: {key} must be true or false")
    return value


def _one(node: Any, depth: int, walk: _Walk, *, top: bool) -> Node:
    if not isinstance(node, Mapping):
        raise MenuError(f"a menu entry must be an object, got {type(node).__name__}")
    kind = node.get("type")
    if kind not in _KINDS:
        raise MenuError(f"unknown entry type {kind!r}; use one of {', '.join(sorted(_KINDS))}")
    if top and kind != "submenu":
        raise MenuError("the menu bar holds menus (type 'submenu'), not single entries")
    walk.entries += 1
    if walk.entries > MAX_ENTRIES:
        raise MenuError(f"a menu may have at most {MAX_ENTRIES} entries")
    unknown = set(node) - _ALLOWED[kind]
    if unknown:
        raise MenuError(f"unknown field(s) for {kind}: {', '.join(sorted(map(str, unknown)))}")
    if kind == "separator":
        return {"type": "separator"}
    label = _text(node, "label", MAX_LABEL, kind)
    where = f"{kind} {label!r}"
    out: Node = {
        "type": kind,
        "label": label,
        "enabled": _flag(node, "enabled", True, where),
        "visible": _flag(node, "visible", True, where),
    }
    ident = node.get("id")
    if ident is None and kind != "submenu":
        raise MenuError(f"{where}: an id is required")
    if ident is not None:
        if not isinstance(ident, str) or not ID.match(ident):
            raise MenuError(
                f"{where}: id must start with a letter and use letters, digits, . _ : -"
            )
        if ident in walk.used:
            raise MenuError(f"{where}: the id {ident!r} is used twice")
        walk.used.add(ident)
        out["id"] = ident
    icon = node.get("icon")
    if icon is not None:
        if not isinstance(icon, str) or not ICON.match(icon) or ".." in icon or "//" in icon:
            raise MenuError(f"{where}: icon must be a path on this app such as /icons/save.svg")
        out["icon"] = icon
    shortcut = node.get("shortcut")
    if shortcut is not None:
        if (
            kind in ("submenu",)
            or not isinstance(shortcut, str)
            or len(shortcut) > MAX_SHORTCUT
            or not SHORTCUT.match(shortcut)
        ):
            raise MenuError(f"{where}: shortcut must be short text such as Ctrl+S")
        out["shortcut"] = shortcut
    if kind in ("check", "radio"):
        out["checked"] = _flag(node, "checked", False, where)
    if kind == "radio":
        group = node.get("group")
        if not isinstance(group, str) or not NAME.match(group):
            raise MenuError(f"{where}: a radio entry needs a group name")
        out["group"] = group
    if kind == "submenu":
        if depth >= MAX_DEPTH:
            raise MenuError(f"menus may nest at most {MAX_DEPTH} levels")
        raw = node.get("items", [])
        if not isinstance(raw, list | tuple):
            raise MenuError(f"{where}: items must be a list")
        out["items"] = _many(raw, depth + 1, walk, top=False)
    return out


def _many(raw: Iterable[Any], depth: int, walk: _Walk, *, top: bool) -> list[Node]:
    entries = [_one(to_node(entry), depth, walk, top=top) for entry in raw]
    seen: set[str] = set()
    for entry in entries:  # radios of one group: only the first one that is on stays on
        if entry["type"] == "radio" and entry["checked"]:
            if entry["group"] in seen:
                entry["checked"] = False
            seen.add(entry["group"])
    return entries


def normalise(raw: Iterable[Any], *, bar: bool = False, used: set[str] | None = None) -> list[Node]:
    """Check a list of entries and return them as plain, complete dictionaries.

    ``bar`` says the list is the top level of a menu bar. ``used`` carries the ids taken so far,
    so ids stay unique across a bar and its context menus.

    Raises:
        MenuError: If anything is not allowed.

    Example:
        >>> normalise([Item("a", "A")])[0]["enabled"]
        True
        >>> normalise([Item("a", "A"), Item("a", "B")])
        Traceback (most recent call last):
        ...
        cornea_menus.model.MenuError: item 'B': the id 'a' is used twice
    """
    return _many(raw, 1, _Walk(set() if used is None else used), top=bar)


def check_context_name(name: str) -> str:
    if not isinstance(name, str) or not NAME.match(name):
        raise MenuError(f"a context menu name must be like 'editor', got {name!r}")
    return name


Mode = Literal["component", "frame"]
THEMES = ("win11", "xp", "office", "macos", "ubuntu")
Theme = Literal["win11", "xp", "office", "macos", "ubuntu"]


@dataclass(frozen=True, slots=True)
class MenuBar:
    """The menus along the top of the window.

    Example:
        >>> MenuBar([Menu("&File", [Item("file.new", "&New")])]).menus[0].label
        '&File'
    """

    menus: tuple[Submenu, ...] | list[Submenu] = field(default_factory=tuple)

    def to_nodes(self) -> list[Node]:
        return [menu.to_node() for menu in self.menus]


@dataclass(frozen=True, slots=True)
class ContextMenu:
    """A menu that opens where the person right-clicks.

    A page element asks for it with ``data-cornea-context="<name>"``. The context menu named
    ``default`` opens everywhere else.

    Example:
        >>> ContextMenu("editor", [Item("edit.copy", "Copy")]).name
        'editor'
    """

    name: str
    items: tuple[Any, ...] | list[Any] = field(default_factory=tuple)
