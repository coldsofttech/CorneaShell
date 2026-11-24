import asyncio
import base64
import hashlib
import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from cornea import Shell
from cornea.core.update import Custom, JsonFeed, Release, UpdateError, Updater
from cornea.core.update import install as install_module
from update_support import Site


def make_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    return buffer.getvalue()


class Events:
    """Collects what the updater tells the page."""

    def __init__(self) -> None:
        self.log: list[tuple[str, Any]] = []

    def __call__(self, event: str, detail: Any = None) -> None:
        self.log.append((event, detail))

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.log]


def make_updater(source: Any, tmp_path: Path, **options: Any) -> tuple[Updater, Events, list[int]]:
    events, exits = Events(), []
    updater = Updater(source, current_version="1.0.0", download_dir=tmp_path / "dl", **options)
    updater.bind(events, lambda: exits.append(1))
    return updater, events, exits


def signing_key() -> tuple[Ed25519PrivateKey, str]:
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, base64.b64encode(raw).decode()


def serve_release(site: Site, data: bytes, **fields: Any) -> JsonFeed:
    site.add("/app-1.1.0.zip", data)
    feed = {"version": "1.1.0", "url": "app-1.1.0.zip", "sha256": site.sha256(data), **fields}
    return JsonFeed(site.add("/feed.json", feed))


# ----- check --------------------------------------------------------------------------------


def test_check_finds_a_newer_release_and_tells_the_page(site: Site, tmp_path: Path) -> None:
    updater, events, _ = make_updater(serve_release(site, b"x"), tmp_path)
    release = updater.check()
    assert release is not None
    assert release.version == "1.1.0"
    assert updater.state == "available"
    assert events.names == ["update-checking", "update-available"]
    assert events.log[-1][1]["version"] == "1.1.0"
    assert "sha256" not in events.log[-1][1]


@pytest.mark.parametrize("version", ["1.0.0", "1.0", "0.9"])
def test_check_ignores_the_same_or_an_older_release(version: str, tmp_path: Path) -> None:
    source = Custom(lambda: Release(version, "https://example.com/a.zip"))
    updater, events, _ = make_updater(source, tmp_path)
    assert updater.check() is None
    assert updater.state == "idle"
    assert events.names[-1] == "update-none"


def test_check_respects_min_version(tmp_path: Path) -> None:
    source = Custom(lambda: Release("3.0", "https://example.com/a.zip", min_version="2.0"))
    updater, events, _ = make_updater(source, tmp_path)
    with pytest.raises(UpdateError, match=r"must first update to 2\.0"):
        updater.check()
    assert events.names[-1] == "update-error"
    assert events.log[-1][1]["stage"] == "check"
    assert updater.state == "error"


def test_check_refuses_hosts_outside_the_allowlist(tmp_path: Path) -> None:
    source = Custom(lambda: Release("2.0", "https://evil.example.net/a.zip"))
    updater, _, _ = make_updater(source, tmp_path, allowed_hosts=("downloads.example.com",))
    with pytest.raises(UpdateError, match="not allowed"):
        updater.check()


def test_a_failing_source_is_an_error_event(tmp_path: Path) -> None:
    def boom() -> None:
        raise OSError("offline")

    updater, events, _ = make_updater(Custom(boom), tmp_path)
    with pytest.raises(UpdateError, match="offline"):
        updater.check()
    assert updater.status()["error"] is not None
    assert events.names[-1] == "update-error"


def test_current_version_must_be_a_version() -> None:
    with pytest.raises(ValueError, match="not a version"):
        Updater(Custom(lambda: None), current_version="latest")


# ----- download and verify ---------------------------------------------------------------------


def test_download_verifies_and_reports_progress(site: Site, tmp_path: Path) -> None:
    data = make_zip({"app.exe": b"x" * 300_000})
    updater, events, _ = make_updater(serve_release(site, data, size=len(data)), tmp_path)
    updater.check()
    path = updater.download()
    assert path.read_bytes() == data
    assert path.parent.name == "1.1.0"
    assert updater.state == "ready"
    assert "update-progress" in events.names
    assert events.names[-1] == "update-verified"
    progress = [d for n, d in events.log if n == "update-progress"]
    assert progress[-1]["percent"] == 100.0
    assert not list(path.parent.glob("*.part"))


def test_a_wrong_checksum_deletes_the_download(site: Site, tmp_path: Path) -> None:
    feed = serve_release(site, b"real", sha256="00" * 32)
    updater, events, _ = make_updater(feed, tmp_path)
    updater.check()
    with pytest.raises(UpdateError, match="checksum") as caught:
        updater.download()
    assert caught.value.stage == "verify"
    assert not list((tmp_path / "dl").rglob("*.zip"))
    assert events.names[-1] == "update-error"


def test_a_checksum_is_required_unless_turned_off(site: Site, tmp_path: Path) -> None:
    site.add("/a.zip", b"data")
    source = Custom(lambda: Release("2.0", site.base + "/a.zip"))
    updater, _, _ = make_updater(source, tmp_path)
    updater.check()
    with pytest.raises(UpdateError, match="no checksum"):
        updater.download()
    relaxed, _, _ = make_updater(source, tmp_path, require_hash=False)
    relaxed.check()
    assert relaxed.download().is_file()


def test_download_needs_a_check_first(tmp_path: Path) -> None:
    updater, _, _ = make_updater(Custom(lambda: None), tmp_path)
    with pytest.raises(UpdateError, match="call check"):
        updater.download()


def test_download_refuses_an_unknown_file_type(site: Site, tmp_path: Path) -> None:
    site.add("/a.sh", b"echo hi")
    source = Custom(lambda: Release("2.0", site.base + "/a.sh", sha256=site.sha256(b"echo hi")))
    updater, _, _ = make_updater(source, tmp_path)
    updater.check()
    with pytest.raises(UpdateError, match="cannot install"):
        updater.download()


def test_download_names_are_made_safe(site: Site, tmp_path: Path) -> None:
    data = make_zip({"a": b"1"})
    site.add("/..%2F..%2Fevil%20name.zip", data)
    source = Custom(
        lambda: Release("2.0", site.base + "/..%2F..%2Fevil%20name.zip", sha256=site.sha256(data))
    )
    updater, _, _ = make_updater(source, tmp_path)
    updater.check()
    path = updater.download()
    assert (tmp_path / "dl") in path.parents
    assert path.name == "_.._evil_name.zip"  # harmless: it is one name inside the folder


def test_an_early_end_is_an_error(site: Site, tmp_path: Path) -> None:
    data = make_zip({"a": b"1"})
    feed = serve_release(site, data, size=len(data) + 50)
    updater, _, _ = make_updater(feed, tmp_path)
    updater.check()
    with pytest.raises(UpdateError, match="not the size"):
        updater.download()


# ----- signed mode --------------------------------------------------------------------------


def sign(private: Ed25519PrivateKey, data: bytes) -> str:
    return base64.b64encode(private.sign(hashlib.sha256(data).digest())).decode()


def test_signed_mode_accepts_a_good_signature(site: Site, tmp_path: Path) -> None:
    private, public = signing_key()
    data = make_zip({"a": b"1"})
    feed = serve_release(site, data, signature=sign(private, data))
    updater, events, _ = make_updater(feed, tmp_path, public_key=public)
    assert updater.signed
    updater.check()
    assert updater.download().is_file()
    assert events.names[-1] == "update-verified"


def test_signed_mode_refuses_a_signature_from_another_key(site: Site, tmp_path: Path) -> None:
    other, _ = signing_key()
    _, public = signing_key()
    data = make_zip({"a": b"1"})
    feed = serve_release(site, data, signature=sign(other, data))
    updater, _, _ = make_updater(feed, tmp_path, public_key=public)
    updater.check()
    with pytest.raises(UpdateError, match="signature is not valid"):
        updater.download()
    assert not list((tmp_path / "dl").rglob("*.zip"))


def test_signed_mode_refuses_tampered_files_even_with_a_matching_hash(
    site: Site, tmp_path: Path
) -> None:
    private, public = signing_key()
    original = make_zip({"a": b"1"})
    tampered = make_zip({"a": b"evil"})
    # The attacker controls the feed and the file, so the checksum agrees; the signature cannot.
    feed = serve_release(site, tampered, signature=sign(private, original))
    updater, _, _ = make_updater(feed, tmp_path, public_key=public)
    updater.check()
    with pytest.raises(UpdateError, match="signature is not valid"):
        updater.download()


def test_signed_mode_refuses_an_unsigned_release(site: Site, tmp_path: Path) -> None:
    _, public = signing_key()
    updater, _, _ = make_updater(serve_release(site, b"zip"), tmp_path, public_key=public)
    updater.check()
    with pytest.raises(UpdateError, match="not signed"):
        updater.download()


def test_a_bad_public_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="public_key"):
        Updater(Custom(lambda: None), current_version="1.0", public_key="not base64!!")
    with pytest.raises(ValueError, match="32 bytes"):
        Updater(
            Custom(lambda: None),
            current_version="1.0",
            public_key=base64.b64encode(b"short").decode(),
        )


# ----- install ------------------------------------------------------------------------------


def test_zip_extraction_flattens_a_single_folder(tmp_path: Path) -> None:
    archive = tmp_path / "u.zip"
    archive.write_bytes(make_zip({"MyApp/app.exe": b"1", "MyApp/lib/x.dll": b"2"}))
    root = install_module.extract_zip(archive, tmp_path / "stage")
    assert root.name == "MyApp"
    assert (root / "lib" / "x.dll").read_bytes() == b"2"


def test_zip_extraction_refuses_paths_that_escape(tmp_path: Path) -> None:
    archive = tmp_path / "u.zip"
    archive.write_bytes(make_zip({"../../evil.txt": b"x"}))
    with pytest.raises(UpdateError, match="unsafe path"):
        install_module.extract_zip(archive, tmp_path / "stage")
    assert not (tmp_path.parent / "evil.txt").exists()


def test_zip_extraction_refuses_a_broken_archive(tmp_path: Path) -> None:
    archive = tmp_path / "u.zip"
    archive.write_bytes(b"not a zip")
    with pytest.raises(UpdateError, match="not a valid zip"):
        install_module.extract_zip(archive, tmp_path / "stage")


def test_install_writes_a_helper_for_a_zip_and_exits(
    site: Site, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[Path] = []
    monkeypatch.setattr(install_module, "spawn_helper", started.append)
    data = make_zip({"MyApp/app.exe": b"new"})
    app_dir = tmp_path / "Program"
    updater, events, exits = make_updater(serve_release(site, data), tmp_path, install_dir=app_dir)
    updater.check()
    updater.download()
    updater.install()
    script = started[0].read_text()
    assert f'robocopy "{tmp_path / "dl" / "1.1.0" / "staging" / "MyApp"}" "{app_dir}"' in script
    assert "tasklist" in script
    assert 'start "" ' in script
    assert (tmp_path / "dl" / "1.1.0" / "staging" / "MyApp" / "app.exe").read_bytes() == b"new"
    assert events.names[-1] == "update-ready"
    assert exits == [1]


@pytest.mark.parametrize(
    ("kind", "name", "switches"),
    [
        ("inno", "Setup.exe", "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-"),
        ("nsis", "Setup.exe", "/S"),
        ("wix", "Setup.exe", "/quiet /norestart"),
    ],
)
def test_install_runs_an_exe_silently_and_waits_for_it(
    kind: str, name: str, switches: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[Path] = []
    monkeypatch.setattr(install_module, "spawn_helper", started.append)
    installer = tmp_path / name
    installer.write_bytes(b"MZ")
    updater, _, exits = make_updater(Custom(lambda: None), tmp_path, installer=kind)
    updater.install(installer)
    lines = started[0].read_text().splitlines()
    assert f'start "" /wait "{installer}" {switches}' in lines
    assert f'>"{tmp_path / "result.txt"}" echo %ERRORLEVEL%' in lines
    assert lines.index(f'start "" /wait "{installer}" {switches}') < next(
        i for i, line in enumerate(lines) if line.startswith('start "" "')
    )
    assert exits == [1]


def test_install_runs_an_msi_quietly_without_naming_the_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[Path] = []
    monkeypatch.setattr(install_module, "spawn_helper", started.append)
    package = tmp_path / "Setup.msi"
    package.write_bytes(b"x")
    updater, _, _ = make_updater(Custom(lambda: None), tmp_path, installer_args=("REINSTALL=ALL",))
    updater.install(package)
    assert f'start "" /wait msiexec /i "{package}" /qn /norestart REINSTALL=ALL' in (
        started[0].read_text().splitlines()
    )


def test_an_exe_installer_must_say_which_tool_made_it(tmp_path: Path) -> None:
    package = tmp_path / "Setup.exe"
    package.write_bytes(b"MZ")
    updater, _, exits = make_updater(Custom(lambda: None), tmp_path)
    with pytest.raises(UpdateError, match="say which tool"):
        updater.install(package)
    assert exits == []


def test_custom_installers_need_their_own_switches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "Setup.exe"
    package.write_bytes(b"MZ")
    updater, _, _ = make_updater(Custom(lambda: None), tmp_path, installer="custom")
    with pytest.raises(UpdateError, match="needs installer_args"):
        updater.install(package)
    started: list[Path] = []
    monkeypatch.setattr(install_module, "spawn_helper", started.append)
    ready, _, _ = make_updater(
        Custom(lambda: None), tmp_path, installer="custom", installer_args=("--quiet",)
    )
    ready.install(package)
    assert f'start "" /wait "{package}" --quiet' in started[0].read_text().splitlines()


def test_installer_kind_must_fit_the_file(tmp_path: Path) -> None:
    exe = tmp_path / "Setup.exe"
    exe.write_bytes(b"MZ")
    msi = tmp_path / "Setup.msi"
    msi.write_bytes(b"x")
    wrong_for_exe, _, _ = make_updater(Custom(lambda: None), tmp_path, installer="msi")
    with pytest.raises(UpdateError, match="does not fit"):
        wrong_for_exe.install(exe)
    wrong_for_msi, _, _ = make_updater(Custom(lambda: None), tmp_path, installer="inno")
    with pytest.raises(UpdateError, match="does not fit"):
        wrong_for_msi.install(msi)


@pytest.mark.parametrize(
    ("text", "ok"), [("0", True), ("3010", True), ("1603", False), ("?", False)]
)
def test_the_outcome_of_the_installer_is_read_once_at_start(
    text: str, ok: bool, tmp_path: Path
) -> None:
    folder = tmp_path / "dl" / "1.1.0"
    folder.mkdir(parents=True)
    (folder / "result.txt").write_text(text + " \r\n")
    updater, _, _ = make_updater(Custom(lambda: None), tmp_path)
    assert updater.last_install is not None
    assert updater.last_install["version"] == "1.1.0"
    assert updater.last_install["ok"] is ok
    assert updater.status()["last_install"] == updater.last_install
    assert not (folder / "result.txt").exists()
    again, _, _ = make_updater(Custom(lambda: None), tmp_path)
    assert again.last_install is None


def test_install_does_not_exit_when_the_helper_cannot_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(script: Path) -> None:
        raise UpdateError("nope", "install")

    monkeypatch.setattr(install_module, "spawn_helper", refuse)
    installer = tmp_path / "Setup.msi"
    installer.write_bytes(b"x")
    updater, events, exits = make_updater(Custom(lambda: None), tmp_path)
    with pytest.raises(UpdateError, match="nope"):
        updater.install(installer)
    assert exits == []
    assert events.names[-1] == "update-error"


def test_install_needs_a_packaged_program_or_a_folder(tmp_path: Path) -> None:
    archive = tmp_path / "u.zip"
    archive.write_bytes(make_zip({"a": b"1"}))
    updater, _, exits = make_updater(Custom(lambda: None), tmp_path)
    with pytest.raises(UpdateError, match="not packaged"):
        updater.install(archive)
    assert exits == []


def test_install_needs_a_shell_to_close(tmp_path: Path) -> None:
    installer = tmp_path / "Setup.exe"
    installer.write_bytes(b"x")
    updater = Updater(Custom(lambda: None), current_version="1.0")
    with pytest.raises(UpdateError, match="given to a Shell"):
        updater.install(installer)


@pytest.mark.parametrize("bad", ['C:\\a"b', "C:\\100%", "C:\\a&b", "C:\\a^b", "a\nb"])
def test_helper_paths_with_batch_syntax_are_refused(bad: str) -> None:
    with pytest.raises(UpdateError, match="character"):
        install_module.check_batch_text(bad, "path")


def test_spawn_helper_is_windows_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    with pytest.raises(UpdateError, match="only works on Windows"):
        install_module.spawn_helper(tmp_path / "x.bat")


def test_update_does_it_all(site: Site, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install_module, "spawn_helper", lambda script: None)
    data = make_zip({"app.exe": b"1"})
    updater, events, exits = make_updater(
        serve_release(site, data), tmp_path, install_dir=tmp_path / "app"
    )
    assert updater.update() is True
    assert events.names[0] == "update-checking"
    assert events.names[-1] == "update-ready"
    assert exits == [1]
    current, _, _ = make_updater(Custom(lambda: None), tmp_path)
    assert current.update() is False


# ----- shell integration -----------------------------------------------------------------------


def call(shell: Shell, name: str) -> Any:
    return asyncio.run(shell.actions.call(name, {}, None))


def test_shell_binds_the_updater_and_relays_events(tmp_path: Path) -> None:
    updater = Updater(
        Custom(lambda: Release("2.0", "https://example.com/a.zip")),
        current_version="1.0",
        download_dir=tmp_path,
    )
    shell = Shell(window=None, update=updater)
    heard: list[str] = []
    shell.notify = lambda event, detail=None: heard.append(event)  # type: ignore[method-assign]
    updater.bind(shell.notify, shell._request_exit)
    updater.check()
    assert heard == ["update-checking", "update-available"]
    assert shell.updater is updater


def test_page_cannot_control_updates_unless_asked(tmp_path: Path) -> None:
    updater = Updater(Custom(lambda: None), current_version="1.0")
    shell = Shell(window=None, update=updater)
    assert not {"check_update", "update_status"} & set(shell.actions.names())


def test_page_control_adds_the_update_actions(tmp_path: Path) -> None:
    release = Release("2.0", "https://example.com/a.zip", notes="Hi")
    updater = Updater(Custom(lambda: release), current_version="1.0", page_control=True)
    shell = Shell(window=None, update=updater)
    names = set(shell.actions.names())
    assert {"check_update", "download_update", "install_update", "update_status"} <= names
    assert call(shell, "update_status")["state"] == "idle"
    assert call(shell, "check_update")["version"] == "2.0"
    status = call(shell, "update_status")
    assert status["state"] == "available"
    assert status["release"]["notes"] == "Hi"


def test_check_on_start_checks_in_the_background(tmp_path: Path) -> None:
    updater = Updater(
        Custom(lambda: Release("2.0", "https://example.com/a.zip")),
        current_version="1.0",
        check_on_start=True,
    )
    shell = Shell(window=None, update=updater)
    with shell:
        shell._check_for_update()
        for _ in range(200):
            if updater.state == "available":
                break
            import time

            time.sleep(0.01)
    assert updater.state == "available"


def test_request_exit_stops_a_windowless_server() -> None:
    shell = Shell(window=None, update=Updater(Custom(lambda: None), current_version="1.0"))
    with shell:
        shell._request_exit()
        assert shell._uvicorn is not None
        assert shell._uvicorn.should_exit
