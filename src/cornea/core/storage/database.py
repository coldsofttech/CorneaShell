"""The app's SQLite database: settings, key-value data and the remembered window.

One table holds everything, with a ``namespace`` column. Values are JSON. Every call opens its own
short connection, so the object is safe to share between threads and there is nothing to close.
SQLite's journal makes a crash mid-write harmless, and a second process can use the same file.
"""

import json
import logging
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
BUSY_TIMEOUT = 5.0
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
MAX_VALUE_BYTES = 1_000_000
_MISSING: Any = object()


class StorageError(RuntimeError):
    """The database could not be used."""


class Database:
    """A SQLite file with one ``entries`` table, created and upgraded on first use."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._ready = False
        self._lock = threading.Lock()

    # ----- the file --------------------------------------------------------------------------

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self._prepare()
        with closing(self._open()) as connection:
            yield connection

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT, isolation_level=None)
        connection.execute(f"PRAGMA busy_timeout = {int(BUSY_TIMEOUT * 1000)}")
        return connection

    def _prepare(self) -> None:
        """Create or upgrade the file once. A file that is not a database is set aside."""
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._upgrade()
            except sqlite3.DatabaseError as exc:
                aside = self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}")
                logger.warning(
                    "The database %s is unusable (%s); moved to %s", self.path, exc, aside
                )
                self.path.replace(aside)
                for suffix in ("-wal", "-shm"):
                    self.path.with_name(self.path.name + suffix).unlink(missing_ok=True)
                self._upgrade()
            self._ready = True

    def _upgrade(self) -> None:
        with closing(self._open()) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise StorageError(
                    f"{self.path} was made by a newer Cornea (schema {version}); "
                    f"this one understands {SCHEMA_VERSION}"
                )
            if version < 1:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = NORMAL")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS entries ("
                    " namespace TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,"
                    " updated REAL NOT NULL, PRIMARY KEY (namespace, key)) WITHOUT ROWID"
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # ----- reading and writing ---------------------------------------------------------------

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """The value, or ``default`` if there is none."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM entries WHERE namespace = ? AND key = ?", (namespace, key)
            ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except ValueError:
            logger.warning("Ignoring an unreadable value for %s/%s", namespace, key)
            return default

    def set(self, namespace: str, key: str, value: Any) -> None:
        """Store a JSON-compatible value, replacing any earlier one."""
        try:
            text = json.dumps(value, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"the value for {key!r} is not JSON-compatible: {exc}") from exc
        if len(text.encode("utf-8")) > MAX_VALUE_BYTES:
            raise ValueError(f"the value for {key!r} is larger than {MAX_VALUE_BYTES} bytes")
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO entries (namespace, key, value, updated) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (namespace, key) DO UPDATE SET"
                " value = excluded.value, updated = excluded.updated",
                (namespace, key, text, time.time()),
            )

    def delete(self, namespace: str, key: str) -> bool:
        """Remove a value. ``True`` if there was one."""
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM entries WHERE namespace = ? AND key = ?", (namespace, key)
            )
            return cursor.rowcount > 0

    def keys(self, namespace: str, prefix: str = "") -> list[str]:
        """The keys that start with ``prefix``, in order."""
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT key FROM entries WHERE namespace = ? AND key LIKE ? ESCAPE '\\'"
                " ORDER BY key",
                (namespace, escaped + "%"),
            ).fetchall()
        return [row[0] for row in rows]

    def clear(self, namespace: str) -> int:
        """Remove every value of a namespace. Returns how many there were."""
        with self._connection() as connection:
            return connection.execute(
                "DELETE FROM entries WHERE namespace = ?", (namespace,)
            ).rowcount


def check_key(key: object) -> str:
    """The key, if it is a usable one: letters, digits and ``. _ : / -``, up to 200 characters."""
    if not isinstance(key, str) or not KEY.match(key):
        raise ValueError(
            "keys start with a letter or digit and use letters, digits and . _ : / - "
            "(up to 200 characters)"
        )
    return key


class Namespace:
    """One named area of the database, used like a small dictionary of JSON values.

    Example:
        >>> import tempfile, pathlib
        >>> area = Namespace(Database(pathlib.Path(tempfile.mkdtemp()) / "app.db"), "demo")
        >>> area.set("theme", "dark")
        >>> area.get("theme"), area.get("missing", "light")
        ('dark', 'light')
        >>> area.keys()
        ['theme']
    """

    def __init__(self, database: Database | Callable[[], Database], name: str) -> None:
        self._source = database
        self.name = name

    @property
    def _database(self) -> Database:
        return self._source() if callable(self._source) else self._source

    def get(self, key: str, default: Any = None) -> Any:
        """The value of ``key``, or ``default``."""
        return self._database.get(self.name, check_key(key), default)

    def set(self, key: str, value: Any) -> None:
        """Store a JSON-compatible value (numbers, strings, booleans, ``None``, lists, dicts)."""
        self._database.set(self.name, check_key(key), value)

    def delete(self, key: str) -> bool:
        """Remove ``key``. ``True`` if it was there."""
        return self._database.delete(self.name, check_key(key))

    def has(self, key: str) -> bool:
        """Whether ``key`` has a value."""
        return self._database.get(self.name, check_key(key), _MISSING) is not _MISSING

    def keys(self, prefix: str = "") -> list[str]:
        """The keys that start with ``prefix``."""
        return self._database.keys(self.name, prefix)

    def items(self, prefix: str = "") -> dict[str, Any]:
        """The keys that start with ``prefix``, with their values."""
        database = self._database
        return {key: database.get(self.name, key) for key in database.keys(self.name, prefix)}

    def clear(self) -> int:
        """Remove everything in this namespace. Returns how many values there were."""
        return self._database.clear(self.name)
