"""Persistent storage for an app: settings, key-value data and secrets.

Settings and data live in one SQLite file in the app's folder (see :class:`AppData`). Secrets live
in Windows Credential Manager. Nothing is opened until it is first used.
"""

import json
import logging
import threading
from typing import Any

from cornea.core.app.appdata import AppData
from cornea.core.storage.credentials import (
    CredentialBackend,
    MemoryCredentials,
    SecretStore,
    SecretsUnavailable,
)
from cornea.core.storage.database import Database, Namespace, StorageError, check_key

logger = logging.getLogger(__name__)

SETTINGS = "settings"
DATA = "store"
WINDOW = "cornea.window"
"""Reserved for Cornea itself; the app's own namespaces are ``settings`` and ``store``."""

__all__ = [
    "AppStorage",
    "CredentialBackend",
    "Database",
    "MemoryCredentials",
    "Namespace",
    "SecretStore",
    "SecretsUnavailable",
    "StorageError",
    "check_key",
]


class AppStorage:
    """Everything one app keeps between runs.

    Example:
        >>> import tempfile, os
        >>> os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
        >>> storage = AppStorage("com.example.notes")
        >>> storage.settings.set("theme", "dark")
        >>> storage.settings.get("theme")
        'dark'
    """

    def __init__(self, app_id: str, *, credentials: CredentialBackend | None = None) -> None:
        self.app_id = app_id
        self._database = Database(AppData.database_path(app_id))
        self._imported = False
        self._import_lock = threading.Lock()
        self.settings: Namespace = Namespace(self.database, SETTINGS)
        """The app's settings, a small dictionary of JSON values."""
        self.data: Namespace = Namespace(self.database, DATA)
        """Everything else the app wants to keep: caches, history, state."""
        self.window: Namespace = Namespace(self.database, WINDOW)
        """Where Cornea remembers the window. Not for the app's own use."""
        self.secrets = SecretStore(app_id, credentials)
        """Passwords and tokens, in Windows Credential Manager."""

    @property
    def path(self) -> Any:
        """The database file."""
        return self._database.path

    def database(self) -> Database:
        """The database, after anything left by an older version has been brought in."""
        if not self._imported:
            with self._import_lock:
                if not self._imported:
                    self._imported = True
                    self._import_legacy()
        return self._database

    def _import_legacy(self) -> None:
        """Bring in ``window.json`` from ``%LOCALAPPDATA%\\Cornea\\<id>``, once.

        The old file is renamed to ``window.json.migrated`` and kept. A file that cannot be read
        is left alone: the window simply opens at its default place.
        """
        old = AppData.legacy_root() / self.app_id / "window.json"
        try:
            if not old.is_file() or self._database.get(WINDOW, "place") is not None:
                return
            place = json.loads(old.read_text(encoding="utf-8"))
            if not isinstance(place, dict):
                return
            self._database.set(WINDOW, "place", place)
            old.replace(old.with_name("window.json.migrated"))
            logger.debug("Moved the remembered window from %s into the database", old)
        except (OSError, ValueError, StorageError):
            logger.debug("Could not import %s", old, exc_info=True)
