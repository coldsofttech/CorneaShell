"""Where an app keeps its files: its database, its logs and the single-instance details.

Everything is under ``%LOCALAPPDATA%\\ColdSoft Technologies\\Cornea\\<name>``, where ``<name>`` is
the app's id::

    <name>\\app.db          settings, key-value data and the remembered window (SQLite)
    <name>\\logs\\cornea.log  the debug log
    <name>\\instance.json   only while the app runs, for the single-instance handshake

Secrets are not here: they are in Windows Credential Manager.
"""

import os
from pathlib import Path

COMPANY = "ColdSoft Technologies"
DATABASE_FILE = "app.db"


class AppData:
    """The folders Cornea writes to, all under the user's local application data."""

    @staticmethod
    def root() -> Path:
        r"""``%LOCALAPPDATA%\ColdSoft Technologies\Cornea``. Not created here."""
        return AppData._local() / COMPANY / "Cornea"

    @staticmethod
    def legacy_root() -> Path:
        r"""``%LOCALAPPDATA%\Cornea``, where versions before the database kept their files."""
        return AppData._local() / "Cornea"

    @staticmethod
    def data_dir(app_id: str) -> Path:
        """The folder for ``app_id``, created on use."""
        folder = AppData.root() / app_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def database_path(app_id: str) -> Path:
        """The app's SQLite file. The folder is created, the file is made on first use."""
        return AppData.data_dir(app_id) / DATABASE_FILE

    @staticmethod
    def logs_dir(app_id: str | None = None) -> Path:
        r"""Where debug mode writes its log: ``<name>\logs``, or ``logs`` beside the apps when
        there is no app id. Not created here."""
        base = AppData.root() / app_id if app_id else AppData.root()
        return base / "logs"

    @staticmethod
    def _local() -> Path:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
