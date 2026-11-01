"""Where an app keeps its files: the remembered window and the single-instance details."""

import os
from pathlib import Path


def data_dir(app_id: str) -> Path:
    """The folder for ``app_id`` under the user's local application data, created on use."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    folder = Path(base) / "Cornea" / app_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder
