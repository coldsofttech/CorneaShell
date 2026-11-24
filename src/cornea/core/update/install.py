"""Put a downloaded update in place and start the new version.

A running Windows program cannot replace its own files, so the app starts a small helper
script, waits for the helper to take over, and exits. The helper waits until the app's process
has gone, copies the new files (or runs the installer) and starts the app again.
"""

import os
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from cornea.core.update.release import UpdateError

INSTALLER_SUFFIXES = frozenset({".exe", ".msi"})
SUPPORTED = frozenset({".zip", *INSTALLER_SUFFIXES})
MAX_EXTRACTED = 8 * 1024**3
SILENT: dict[str, tuple[str, ...]] = {
    "inno": ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"),
    "nsis": ("/S",),
    "wix": ("/quiet", "/norestart"),
    "msi": ("/qn", "/norestart"),
}
"""The switches that make each kind of installer run without showing anything."""
INSTALLER_KINDS = (*SILENT, "custom")
SUCCESS_CODES = frozenset({0, 1641, 3010})
"""Exit codes that mean the installer worked (1641 and 3010: a restart is needed)."""
_UNSAFE = re.compile(r'[\x00-\x1f"%^&|<>!`]')
"""Characters that mean something to ``cmd`` and cannot be quoted safely in a batch file."""


def installer_arguments(kind: str, suffix: str, extra: tuple[str, ...]) -> tuple[str, ...]:
    """The command-line switches for a silent install, then any ``extra`` ones.

    ``auto`` means ``msi`` for an ``.msi`` file. An ``.exe`` could be built by any tool with its
    own switches, so it must be named; ``custom`` takes only the switches in ``extra``.

    Raises:
        UpdateError: If the installer kind is not known, does not fit the file, or is needed.
    """
    if kind == "auto":
        if suffix != ".msi":
            raise UpdateError(
                "say which tool built the installer: installer='inno', 'nsis', 'wix' or 'custom'",
                "install",
            )
        kind = "msi"
    if kind not in INSTALLER_KINDS:
        raise UpdateError(f"unknown installer {kind!r}; use one of {INSTALLER_KINDS}", "install")
    if (kind == "msi") != (suffix == ".msi") and kind != "custom":
        raise UpdateError(f"installer={kind!r} does not fit a {suffix} file", "install")
    if kind == "custom":
        if not extra:
            raise UpdateError(
                "installer='custom' needs installer_args with the silent switches", "install"
            )
        return extra
    return (*SILENT[kind], *extra)


def read_result(folder: Path) -> dict[str, object] | None:
    """The outcome the helper wrote for the newest finished install under ``folder``, once.

    The file is deleted when read, so each outcome is reported one time.
    """
    results = sorted(folder.glob("*/result.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not results:
        return None
    newest = results[0]
    try:
        code = int(newest.read_text(encoding="utf-8-sig").strip())
    except (OSError, ValueError):
        code = -1
    version = newest.parent.name
    for path in results:
        path.unlink(missing_ok=True)
    return {"version": version, "exit_code": code, "ok": code in SUCCESS_CODES}


def check_batch_text(value: str, what: str) -> str:
    """Refuse text that a batch file could misread. A path with these characters cannot be used."""
    if _UNSAFE.search(value):
        raise UpdateError(f"the {what} has a character the installer cannot handle", "install")
    return value


def is_packaged() -> bool:
    """Whether this is a frozen program (PyInstaller), which has its own folder to replace."""
    return bool(getattr(sys, "frozen", False))


def default_install_dir() -> Path | None:
    """The folder of the frozen program, or ``None`` when running from source."""
    return Path(sys.executable).resolve().parent if is_packaged() else None


def relaunch_command() -> list[str]:
    """The command that starts this app again: the program itself, or ``python script args``."""
    if is_packaged():
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, *sys.argv]


def extract_zip(archive: Path, staging: Path) -> Path:
    """Unpack ``archive`` into ``staging`` and return the folder that holds the app's files.

    Refuses paths that climb out of the folder, absolute paths, and absurd sizes. When the
    archive wraps everything in one folder, that folder is returned.
    """
    root = staging.resolve()
    try:
        with zipfile.ZipFile(archive) as bundle:
            total = 0
            for member in bundle.infolist():
                target = (root / member.filename).resolve()
                if target != root and root not in target.parents:
                    raise UpdateError("the update archive has an unsafe path", "install")
                total += member.file_size
                if total > MAX_EXTRACTED:
                    raise UpdateError("the update archive is too large to unpack", "install")
            bundle.extractall(root)
    except zipfile.BadZipFile as exc:
        raise UpdateError("the update is not a valid zip file", "install") from exc
    entries = [entry for entry in root.iterdir() if entry.name != "__MACOSX"]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return root


@dataclass(frozen=True, slots=True)
class InstallPlan:
    """What the helper will do once the app has exited."""

    script: Path
    """Where the batch file is written."""
    pid: int
    """The process to wait for."""
    action: str
    """``copy`` the unpacked files over the install folder, or ``run`` an installer."""
    source: Path
    """The unpacked folder, or the installer."""
    install_dir: Path | None
    relaunch: list[str]
    installer_args: tuple[str, ...] = ()
    result: Path | None = None
    """Where the helper writes the installer's exit code, for the next start to read."""

    def render(self) -> str:
        """The batch file's text."""
        lines = [
            "@echo off",
            "setlocal",
            f'set "PID={self.pid}"',
            ":wait",
            'tasklist /FI "PID eq %PID%" 2>NUL | find "%PID%" >NUL',
            "if not errorlevel 1 (",
            "  timeout /t 1 /nobreak >NUL",
            "  goto wait",
            ")",
        ]
        if self.action == "copy":
            assert self.install_dir is not None  # noqa: S101
            options = "/E /R:10 /W:1 /NFL /NDL /NJH /NJS"
            lines.append(f'robocopy "{self.source}" "{self.install_dir}" {options} >NUL')
        else:
            args = " ".join(self.installer_args)
            program = (
                f'msiexec /i "{self.source}"'
                if self.source.suffix.lower() == ".msi"
                else f'"{self.source}"'
            )
            lines.append(f'start "" /wait {program} {args}'.rstrip())
            if self.result is not None:
                lines.append(f'>"{self.result}" echo %ERRORLEVEL%')
        command = " ".join(f'"{part}"' for part in self.relaunch)
        lines += [f'start "" {command}', '(goto) 2>NUL & del "%~f0"']
        return "\r\n".join(lines) + "\r\n"

    def write(self) -> Path:
        """Write the script, after checking every path and argument that goes into it."""
        for path in (self.script, self.source, *(p for p in (self.install_dir, self.result) if p)):
            check_batch_text(str(path), "update path")
        for part in (*self.relaunch, *self.installer_args):
            check_batch_text(part, "start-up command")
        self.script.write_text(self.render(), encoding="utf-8", newline="")
        return self.script


def spawn_helper(script: Path) -> None:
    """Start the helper script detached from this process. Windows only.

    Raises:
        UpdateError: If this is not Windows or the helper could not be started.
    """
    if sys.platform != "win32":
        raise UpdateError("installing an update only works on Windows", "install")
    flags = (
        subprocess.DETACHED_PROCESS  # type: ignore[attr-defined,unused-ignore]
        | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined,unused-ignore]
        | subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined,unused-ignore]
    )
    try:
        subprocess.Popen(  # noqa: S603 - a script this module wrote, with checked paths
            [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(script)],
            creationflags=flags,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError(f"could not start the installer helper: {exc}", "install") from exc


def current_pid() -> int:
    return os.getpid()
