"""Menu bars, context menus and title bars for Cornea Shell pages.

Python (or the page) declares the menus as data; the page draws them in the style you pick and
sends clicks back. Nothing is drawn by Windows, so the same menus work in a frameless window and
in every theme.

Example:
    >>> from cornea_menus import Item, Menu, MenuBar, Menus
    >>> menus = Menus(MenuBar([Menu("&File", [Item("file.quit", "&Quit", shortcut="Ctrl+Q")])]))
    >>> menus.theme
    'win11'
"""

__version__ = "0.1.0"

from cornea_menus.model import (
    THEMES,
    Check,
    ContextMenu,
    Item,
    Menu,
    MenuBar,
    MenuError,
    Radio,
    Separator,
    Submenu,
)
from cornea_menus.service import MenuClick, Menus

__all__ = [
    "THEMES",
    "Check",
    "ContextMenu",
    "Item",
    "Menu",
    "MenuBar",
    "MenuClick",
    "MenuError",
    "Menus",
    "Radio",
    "Separator",
    "Submenu",
    "__version__",
]
