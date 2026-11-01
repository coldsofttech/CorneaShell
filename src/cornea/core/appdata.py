"""Where an app keeps its files: the remembered window and the single-instance details."""

import os
from pathlib import Path


def logs_dir() -> Path:
    """Where debug mode writes its log, ``%LOCALAPPDATA%\\Cornea\\logs``. Not created here."""
    return _cornea_dir() / "logs"


def _cornea_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Cornea"


def data_dir(app_id: str) -> Path:
    """The folder for ``app_id`` under the user's local application data, created on use."""
    folder = _cornea_dir() / app_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder
