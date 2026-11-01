"""Where an app keeps its files: the remembered window and the single-instance details."""

import os
from pathlib import Path


class AppData:
    """The folders Cornea writes to, all under the user's local application data."""

    @staticmethod
    def logs_dir() -> Path:
        r"""Where debug mode writes its log, ``%LOCALAPPDATA%\Cornea\logs``. Not created here."""
        return AppData._cornea_dir() / "logs"

    @staticmethod
    def data_dir(app_id: str) -> Path:
        """The folder for ``app_id`` under the user's local application data, created on use."""
        folder = AppData._cornea_dir() / app_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def _cornea_dir() -> Path:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Cornea"
