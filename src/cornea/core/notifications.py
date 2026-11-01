"""Windows toast notifications, shown by Windows itself.

The page (or your Python code) gives a title and a message; Windows draws and places the toast,
so its look cannot be changed from here. This needs the optional ``notifications`` extra
(``pip install "cornea-shell[notifications]"``), which brings the Windows runtime bindings.

A toast belongs to an app identity. The app's id (``App(id=...)``) is used when there is one,
otherwise ``Cornea.Shell``. The identity is registered for the current user under
``HKEY_CURRENT_USER\\Software\\Classes\\AppUserModelId``, with the window title as its name and
the window icon as its icon, so the toast shows those instead of "Python".
"""

import logging
import re
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from cornea.core.window import Unavailable

logger = logging.getLogger(__name__)

MAX_TITLE = 64
MAX_MESSAGE = 256
MAX_ID = 64
NOTIFICATION_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")
DEFAULT_APP_ID = "Cornea.Shell"
INSTALL_HINT = 'Notifications need the extra: pip install "cornea-shell[notifications]"'

_REGISTRY_ROOT = r"Software\Classes\AppUserModelId"
_alive: set[Any] = set()
"""Toasts that are still on screen. Windows calls back into them, so they must not be freed."""
_alive_lock = threading.Lock()


def check_notification(title: object, message: object, notification_id: object = None) -> None:
    """Refuse anything that is not a short plain-text title and message.

    Raises:
        ValueError: With what is wrong.
    """
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")
    if len(title) > MAX_TITLE:
        raise ValueError(f"title can have at most {MAX_TITLE} characters")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")
    if len(message) > MAX_MESSAGE:
        raise ValueError(f"message can have at most {MAX_MESSAGE} characters")
    if notification_id is not None and (
        not isinstance(notification_id, str)
        or len(notification_id) > MAX_ID
        or not NOTIFICATION_ID.match(notification_id)
    ):
        raise ValueError(
            f"notification_id must be up to {MAX_ID} letters, digits and . _ : - characters"
        )


def toast_xml(title: str, message: str) -> str:
    """The toast as XML. The text is escaped, so it can never add markup."""
    return (
        '<toast><visual><binding template="ToastGeneric">'
        f"<text>{escape(title)}</text><text>{escape(message)}</text>"
        "</binding></visual></toast>"
    )


class Notifier:
    """Shows toasts for one app identity."""

    def __init__(self, app_id: str | None, name: str, icon: Path | str | None = None) -> None:
        self.app_id = app_id or DEFAULT_APP_ID
        self.name = name
        self.icon = Path(icon).resolve() if icon is not None else None
        self._registered = False

    def show(self, title: str, message: str, on_click: Callable[[], None] | None = None) -> None:
        """Show a toast. ``on_click`` runs, on another thread, if the person clicks it."""
        check_notification(title, message)
        if sys.platform != "win32":
            raise Unavailable("Notifications only work on Windows for now.")
        try:
            from winrt.windows.data.xml.dom import XmlDocument
            from winrt.windows.ui.notifications import ToastNotification, ToastNotificationManager
        except ImportError as exc:
            raise Unavailable(INSTALL_HINT) from exc
        self._register()
        document = XmlDocument()
        document.load_xml(toast_xml(title, message))
        toast = ToastNotification(document)
        with _alive_lock:
            _alive.add(toast)

        def forget(*_: Any) -> None:
            with _alive_lock:
                _alive.discard(toast)

        def activated(*_: Any) -> None:
            forget()
            if on_click is not None:
                try:
                    on_click()
                except Exception:
                    logger.exception("Handling a notification click failed")

        toast.add_activated(activated)
        toast.add_dismissed(forget)
        toast.add_failed(forget)
        ToastNotificationManager.create_toast_notifier_with_id(self.app_id).show(toast)
        logger.debug("Showed a notification for %s", self.app_id)

    def _register(self) -> None:
        """Give the identity a name and an icon, once. Only the current user's registry is used."""
        if self._registered:
            return
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{_REGISTRY_ROOT}\\{self.app_id}") as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, self.name)
            if self.icon is not None:
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(self.icon))
        self._registered = True
