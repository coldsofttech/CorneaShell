"""The checks behind ``cornea doctor``: is this machine ready to show a Cornea window?"""

import importlib.metadata
import importlib.util
import platform
import socket
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cornea.cli import config
from cornea.core.app.appdata import AppData

Status = Literal["ok", "warn", "fail"]


@dataclass(frozen=True)
class Check:
    """One line of the report."""

    name: str
    status: Status
    detail: str


def run_checks(*, port: int = 0, start: Path | None = None) -> list[Check]:
    """Run every check. A ``fail`` means Cornea cannot work; a ``warn`` is worth knowing."""
    checks = [_cornea(), _python(), _platform()]
    if sys.platform == "win32":
        checks += [_webview2(), _pywebview()]
    checks += [_extras(), _settings_file(start or Path.cwd()), _port(port), _log_folder()]
    return checks


def _cornea() -> Check:
    from cornea import __version__

    return Check("Cornea", "ok", __version__)


def _python() -> Check:
    # The package itself requires 3.11 or newer, so an older Python never gets this far.
    return Check("Python", "ok", ".".join(str(part) for part in sys.version_info[:3]))


def _platform() -> Check:
    name = platform.platform()
    if sys.platform == "win32":
        return Check("Platform", "ok", name)
    return Check(
        "Platform", "warn", f"{name}: windows only work on Windows; `serve` works anywhere"
    )


def _webview2() -> Check:
    from cornea.core.window.window import WEBVIEW2_DOWNLOAD, _registry_version

    version = _registry_version()
    if version is None:
        return Check("WebView2 runtime", "fail", f"not installed; get it from {WEBVIEW2_DOWNLOAD}")
    return Check("WebView2 runtime", "ok", version)


def _pywebview() -> Check:
    try:
        version = importlib.metadata.version("pywebview")
    except importlib.metadata.PackageNotFoundError:
        return Check("pywebview", "fail", "not installed; reinstall with pip install cornea-shell")
    return Check("pywebview", "ok", version)


def _extras() -> Check:
    wanted = {
        "proxy": "httpx",
        "wsgi": "a2wsgi",
        "notifications": "winrt.windows.ui.notifications",
    }
    missing = []
    for extra, module in wanted.items():
        try:
            found = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            found = False
        if not found:
            missing.append(extra)
    if missing:
        return Check("Optional extras", "ok", "not installed: " + ", ".join(missing))
    return Check("Optional extras", "ok", "proxy, wsgi, notifications")


def _settings_file(start: Path) -> Check:
    found = config.find_config(start)
    if found is None:
        return Check("Settings file", "ok", "none found (cornea.toml or [tool.cornea])")
    try:
        config.load_config(found)
    except config.ConfigError as exc:
        return Check("Settings file", "fail", str(exc))
    return Check("Settings file", "ok", f"{found} is valid")


def _port(port: int) -> Check:
    label = f"Port {port}" if port else "Loopback port"
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    except OSError as exc:
        return Check(label, "fail", f"cannot listen on 127.0.0.1:{port}: {exc}")
    return Check(label, "ok", "free" if port else "a free port can be opened")


def _log_folder() -> Check:
    folder = AppData.logs_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=folder):
            pass
    except OSError as exc:
        return Check(
            "Log folder", "warn", f"{folder} is not writable ({exc}); debug logs go to the screen"
        )
    return Check("Log folder", "ok", f"{folder} is writable")
