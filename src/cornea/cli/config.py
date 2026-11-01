"""Settings for the ``cornea`` command from a file, so they need not be typed every time.

The file is ``cornea.toml``, or the ``[tool.cornea]`` table of ``pyproject.toml``. It is searched
for in the current folder and then in each folder above it, and the first one found is used
(files are never merged). Only the command line reads it: the Python API stays explicit.

Each table holds the long flags of ``open`` and ``serve`` without the leading dashes::

    [source]
    run = "npm run dev"
    url = "http://localhost:5173"
    mode = "proxy"

    [window]
    title = "My App"
    frameless = true

A flag given on the command line always wins over the file.
"""

import tomllib
from pathlib import Path
from typing import Any

FILE_NAME = "cornea.toml"
PYPROJECT = "pyproject.toml"

SECTIONS: dict[str, dict[str, str]] = {
    "source": {
        "web-dist": "web_dist",
        "url": "url",
        "mode": "mode",
        "run": "run",
        "run-cwd": "run_cwd",
        "run-timeout": "run_timeout",
        "asgi": "asgi",
        "wsgi": "wsgi",
        "app-dir": "app_dir",
        "package": "package",
        "package-path": "package_path",
        "spa": "spa",
        "hashed-prefix": "hashed_prefix",
    },
    "server": {"host": "host", "port": "port"},
    "security": {
        "allowed-host": "allowed_host",
        "csp": "csp",
        "csp-profile": "csp_profile",
        "api-prefix": "api_prefix",
        "token-ttl": "token_ttl",
        "cookie-samesite": "cookie_samesite",
        "public-path": "public_path",
        "require-origin": "require_origin",
    },
    "bridge": {
        "disable-action": "disable_action",
        "open-files": "open_files",
        "notifications": "notifications",
    },
    "window": {
        "title": "title",
        "size": "size",
        "min-size": "min_size",
        "position": "position",
        "frameless": "frameless",
        "resizable": "resizable",
        "on-top": "on_top",
        "context-menu": "context_menu",
        "devtools": "devtools",
        "debug": "debug",
        "js-api": "js_api",
        "drop-files": "drop_files",
        "downloads": "downloads",
        "icon": "icon",
    },
    "app": {
        "id": "app_id",
        "single-instance": "single_instance",
        "remember-window": "remember_window",
    },
    "logging": {"level": "log_level", "file": "log_file"},
}
"""For each table, the keys it accepts and the command parameter each one sets."""

LIST_PARAMETERS = {"allowed_host", "public_path", "disable_action"}
"""Parameters that take several values: the file may give one string or a list."""

PATH_PARAMETERS = {"web_dist", "run_cwd", "app_dir", "icon", "log_file"}
"""Paths in the file are relative to the file, not to where the command runs."""

SOURCE_PARAMETERS = frozenset(SECTIONS["source"].values())


class ConfigError(ValueError):
    """The settings file cannot be used."""


def find_config(start: Path) -> Path | None:
    """The settings file that applies to ``start``: look here, then in each parent folder."""
    for folder in (start, *start.parents):
        candidate = folder / FILE_NAME
        if candidate.is_file():
            return candidate
        pyproject = folder / PYPROJECT
        if pyproject.is_file() and _tool_table(pyproject) is not None:
            return pyproject
    return None


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc


def _tool_table(path: Path) -> dict[str, Any] | None:
    try:
        table = _read(path).get("tool", {}).get("cornea")
    except ConfigError:
        return None  # a broken pyproject.toml is not ours to complain about when searching
    return table if isinstance(table, dict) else None


def load_config(path: Path) -> dict[str, dict[str, Any]]:
    """Read ``path`` and return it as defaults for the ``open`` and ``serve`` commands.

    Raises:
        ConfigError: If the file cannot be read, or has a table, a key or a value it does not
            understand.
    """
    if path.name == PYPROJECT:
        table = _read(path).get("tool", {}).get("cornea")
        if not isinstance(table, dict):
            raise ConfigError(f"{path} has no [tool.cornea] table")
    else:
        table = _read(path)
    values: dict[str, Any] = {}
    for section, entries in table.items():
        keys = SECTIONS.get(section)
        if keys is None or not isinstance(entries, dict):
            raise ConfigError(
                f"{path}: unknown table [{section}]; use {', '.join(f'[{n}]' for n in SECTIONS)}"
            )
        for key, value in entries.items():
            name = keys.get(key.replace("_", "-"))
            if name is None:
                raise ConfigError(
                    f"{path}: unknown key {key!r} in [{section}]; use {', '.join(keys)}"
                )
            values[name] = _convert(name, value, path.parent)
    return {"open": values, "serve": dict(values)}


def _convert(name: str, value: Any, folder: Path) -> Any:
    if name in LIST_PARAMETERS:
        items = value if isinstance(value, list) else [value]
        return [str(item) for item in items]
    if name in PATH_PARAMETERS:
        return str((folder / str(value)).resolve())
    return value
