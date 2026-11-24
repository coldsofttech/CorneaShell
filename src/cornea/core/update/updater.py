"""The updater: check a source, download, verify, and restart into the new version."""

import logging
import re
import shutil
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from cornea.core.update import http, install, verify
from cornea.core.update.release import Release, UpdateError
from cornea.core.update.sources import UpdateSource
from cornea.core.update.version import is_newer, parse_version

logger = logging.getLogger(__name__)

NotifyFunction = Callable[[str, Any], None]
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


class Updater:
    """Keeps an app up to date from one :class:`~cornea.core.update.sources.UpdateSource`.

    The steps are separate so an app can run them on its own terms: :meth:`check` asks the
    source, :meth:`download` fetches and verifies the file, :meth:`install` hands over to a
    helper that replaces the files and starts the new version. :meth:`update` does all three.
    Progress goes to the page as ``cornea:update-*`` events (see below) when the updater is
    given to a :class:`~cornea.core.shell.Shell`.

    **Verification.** A SHA-256 from the source is always checked, and is required unless
    ``require_hash=False``. A checksum served next to the file only catches a damaged download:
    anyone who can change the feed can change both. For updates you can trust, pass
    ``public_key`` (a base64 Ed25519 key); every release must then carry a ``signature`` of the
    file's SHA-256 digest that this key accepts, and anything else is refused. Needs the
    ``signed-updates`` extra.

    **Events** on the page's ``window``, each with the detail shown: ``cornea:update-checking``,
    ``update-none`` (``{"version"}``), ``update-available`` (the release), ``update-progress``
    (``{"received", "total", "percent"}``), ``update-verified``, ``update-ready`` (the app is
    about to restart) and ``update-error`` (``{"stage", "message"}``).

    Example:
        >>> from cornea.core.update.sources import Custom
        >>> updater = Updater(Custom(lambda: None), current_version="1.0.0")
        >>> updater.check() is None
        True
    """

    def __init__(
        self,
        source: UpdateSource,
        *,
        current_version: str,
        public_key: str | None = None,
        require_hash: bool = True,
        allowed_hosts: tuple[str, ...] = (),
        install_dir: Path | str | None = None,
        installer_args: tuple[str, ...] = (),
        download_dir: Path | str | None = None,
        check_on_start: bool = False,
        page_control: bool = False,
    ) -> None:
        parse_version(current_version)
        self.source = source
        self.current_version = current_version
        self._public_key = verify.decode_public_key(public_key) if public_key else None
        self.require_hash = require_hash
        self.allowed_hosts = tuple(host.strip().lower() for host in allowed_hosts)
        if not all(self.allowed_hosts):
            raise ValueError("allowed_hosts must not contain empty values")
        self.install_dir = Path(install_dir) if install_dir is not None else None
        self.installer_args = installer_args
        self.download_dir = Path(download_dir) if download_dir is not None else None
        self.check_on_start = check_on_start
        self.page_control = page_control
        self.release: Release | None = None
        """The newer release found by the last :meth:`check`, if any."""
        self.downloaded: Path | None = None
        """The verified file from the last :meth:`download`, if any."""
        self.state = "idle"
        """``idle``, ``checking``, ``available``, ``downloading``, ``ready`` or ``error``."""
        self.error: str | None = None
        self._notify: NotifyFunction | None = None
        self._exit: Callable[[], None] | None = None
        self._lock = threading.Lock()

    @property
    def signed(self) -> bool:
        """Whether signed-update mode is on."""
        return self._public_key is not None

    # ----- wiring ---------------------------------------------------------------------------

    def bind(
        self,
        notify: NotifyFunction,
        exit_app: Callable[[], None],
        data_dir: Path | None = None,
    ) -> None:
        """Connect the updater to a running app. :class:`~cornea.core.shell.Shell` does this.

        ``notify`` sends an event to the page, ``exit_app`` closes the app so the helper can
        replace its files, and ``data_dir`` is where downloads go unless ``download_dir`` is set.
        """
        self._notify = notify
        self._exit = exit_app
        if self.download_dir is None and data_dir is not None:
            self.download_dir = data_dir / "updates"

    def status(self) -> dict[str, Any]:
        """Where the updater is now, as JSON, for a page that loaded after an event was sent."""
        return {
            "state": self.state,
            "current_version": self.current_version,
            "release": self.release.as_dict() if self.release else None,
            "error": self.error,
            "signed": self.signed,
        }

    def _emit(self, event: str, detail: Any = None) -> None:
        if self._notify is None:
            return
        try:
            self._notify(event, detail)
        except Exception:
            logger.debug("Could not send the %r event", event, exc_info=True)

    def _fail(self, error: UpdateError) -> UpdateError:
        self.state, self.error = "error", str(error)
        logger.info("Update failed (%s): %s", error.stage, error)
        self._emit("update-error", {"stage": error.stage, "message": str(error)})
        return error

    # ----- the steps ------------------------------------------------------------------------

    def check(self) -> Release | None:
        """Ask the source. Returns the release if it is newer than ``current_version``.

        Raises:
            UpdateError: If the source cannot be read or what it says is not usable.
        """
        with self._lock:
            self.state, self.error = "checking", None
            self._emit("update-checking")
            try:
                release = self.source.latest()
                if release is not None:
                    self._check_host(release)
                    if release.min_version and is_newer(release.min_version, self.current_version):
                        raise UpdateError(
                            f"version {self.current_version} must first update to "
                            f"{release.min_version} or later",
                            "check",
                        )
            except UpdateError as exc:
                raise self._fail(exc) from exc
            except ValueError as exc:
                raise self._fail(
                    UpdateError(f"the update source is not usable: {exc}", "check")
                ) from exc
            if release is None or not is_newer(release.version, self.current_version):
                self.release, self.state = None, "idle"
                self._emit("update-none", {"version": self.current_version})
                return None
            self.release, self.state = release, "available"
            self._emit("update-available", release.as_dict())
            return release

    def download(self, release: Release | None = None) -> Path:
        """Download ``release`` (default: the one :meth:`check` found) and verify it.

        Raises:
            UpdateError: If there is nothing to download, the download fails, or the file does
                not match its checksum or signature. A file that fails is deleted.
        """
        with self._lock:
            release = release or self.release
            if release is None:
                raise self._fail(
                    UpdateError("there is no update to download; call check()", "download")
                )
            target: Path | None = None
            try:
                self._check_host(release)
                self._check_policy(release)
                target = self._target(release)
                self.state, self.error = "downloading", None
                logger.debug("Downloading update %s", release.version)
                digest = http.download(
                    release.url,
                    target,
                    expected_size=release.size,
                    progress=self._progress,
                )
                self._verify(release, target, digest)
            except UpdateError as exc:
                if target is not None:
                    target.unlink(missing_ok=True)
                raise self._fail(exc) from exc
            self.downloaded, self.state = target, "ready"
            self._emit("update-verified", release.as_dict())
            return target

    def install(self, path: Path | None = None) -> None:
        """Replace the app's files with the downloaded update and restart into it.

        This starts a helper, tells the page (``update-ready``) and closes the app; the helper
        waits for it to exit, copies the files and starts the new version. It needs a
        :class:`~cornea.core.shell.Shell` (to close) and a packaged program (or ``install_dir``).

        Raises:
            UpdateError: If nothing was downloaded, the file cannot be installed here, or the
                helper cannot start. Nothing is closed in that case.
        """
        with self._lock:
            try:
                package = path or self.downloaded
                if package is None or not package.is_file():
                    raise UpdateError("there is no downloaded update; call download()", "install")
                if self._exit is None:
                    raise UpdateError(
                        "the updater must be given to a Shell to restart it", "install"
                    )
                script = self._prepare(package)
                install.spawn_helper(script)
            except UpdateError as exc:
                raise self._fail(exc) from exc
            self._emit("update-ready", {"version": self.release.version if self.release else None})
            self._exit()

    def update(self) -> bool:
        """Check, download, verify and install. Returns ``False`` when already up to date."""
        release = self.check()
        if release is None:
            return False
        self.download(release)
        self.install()
        return True

    # ----- internals ------------------------------------------------------------------------

    def _check_host(self, release: Release) -> None:
        host = (urlsplit(release.url).hostname or "").lower()
        if self.allowed_hosts and host not in self.allowed_hosts:
            raise UpdateError(f"downloads from {host} are not allowed", "check")

    def _check_policy(self, release: Release) -> None:
        if self._public_key is not None and not release.signature:
            raise UpdateError(
                "the release is not signed, and signed updates are required", "verify"
            )
        if self.require_hash and self._public_key is None and not release.sha256:
            raise UpdateError("the release has no checksum to verify it with", "verify")

    def _target(self, release: Release) -> Path:
        folder = self.download_dir or Path(tempfile.gettempdir()) / "cornea-updates"
        name = unquote(Path(urlsplit(release.url).path).name)
        name = SAFE_NAME.sub("_", name).lstrip(".") or "update"
        if Path(name).suffix.lower() not in install.SUPPORTED:
            raise UpdateError(
                f"cannot install a {Path(name).suffix or 'file without a type'}; "
                "use .zip, .exe or .msi",
                "download",
            )
        return folder / SAFE_NAME.sub("_", release.version) / name

    def _progress(self, received: int, total: int | None) -> None:
        percent = round(received * 100 / total, 1) if total else None
        self.state = "downloading"
        self._emit("update-progress", {"received": received, "total": total, "percent": percent})

    def _verify(self, release: Release, target: Path, digest_hex: str) -> None:
        if release.sha256 is not None:
            verify.check_hash(digest_hex, release.sha256)
        if self._public_key is not None:
            assert release.signature is not None  # noqa: S101 - _check_policy ensured it
            verify.check_signature(bytes.fromhex(digest_hex), release.signature, self._public_key)

    def _prepare(self, package: Path) -> Path:
        """Unpack a zip (or note the installer) and write the helper script."""
        suffix = package.suffix.lower()
        if suffix not in install.SUPPORTED:
            raise UpdateError("that file type cannot be installed", "install")
        if suffix == ".zip":
            folder = self.install_dir or install.default_install_dir()
            if folder is None:
                raise UpdateError(
                    "this program is not packaged; pass install_dir to say where to put the update",
                    "install",
                )
            staging = package.parent / "staging"
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True)
            source, action = install.extract_zip(package, staging), "copy"
        else:
            folder, source, action = self.install_dir, package, "run"
        plan = install.InstallPlan(
            script=package.parent / "apply-update.bat",
            pid=install.current_pid(),
            action=action,
            source=source,
            install_dir=folder,
            relaunch=install.relaunch_command(),
            installer_args=self.installer_args,
        )
        return plan.write()
