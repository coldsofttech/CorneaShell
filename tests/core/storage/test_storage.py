"""Persistent storage: the database, the secrets, the old-folder import and the page's actions."""

import asyncio
import ctypes
import json
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from cornea import App, Bridge, Shell, create_app
from cornea.core.app import AppData
from cornea.core.bridge.bridge import ActionRegistry
from cornea.core.logs import Logs
from cornea.core.storage import AppStorage, MemoryCredentials, SecretStore, SecretsUnavailable
from cornea.core.storage.credentials import MAX_SECRET_BYTES, WindowsCredentialBackend
from cornea.core.storage.database import MAX_VALUE_BYTES, SCHEMA_VERSION, Database, StorageError


@pytest.fixture(autouse=True)
def local_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    return tmp_path / "local"


@pytest.fixture
def storage() -> AppStorage:
    return AppStorage("notes", credentials=MemoryCredentials())


# ----- where things live ----------------------------------------------------------------------


def test_everything_is_under_the_company_folder(local_data: Path) -> None:
    root = local_data / "ColdSoft Technologies" / "Cornea"

    assert AppData.root() == root
    assert AppData.data_dir("notes") == root / "notes"
    assert AppData.database_path("notes") == root / "notes" / "app.db"
    assert AppData.logs_dir("notes") == root / "notes" / "logs"
    assert AppData.logs_dir() == root / "logs"
    assert AppData.legacy_root() == local_data / "Cornea"


def test_debug_logs_go_beside_the_apps_database(local_data: Path) -> None:
    assert Logs.default_log_file("notes") == (
        local_data / "ColdSoft Technologies" / "Cornea" / "notes" / "logs" / "cornea.log"
    )
    assert Logs.default_log_file().parent.name == "logs"


# ----- the database ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value", [1, 2.5, "text", True, None, [1, "a", None], {"a": {"b": [1, 2]}}, "ünï ☃"]
)
def test_json_values_round_trip(storage: AppStorage, value: Any) -> None:
    storage.data.set("key", value)

    assert storage.data.get("key") == value


def test_a_missing_key_gives_the_default(storage: AppStorage) -> None:
    assert storage.data.get("nothing") is None
    assert storage.data.get("nothing", 7) == 7
    assert storage.data.has("nothing") is False


def test_a_stored_none_is_not_missing(storage: AppStorage) -> None:
    storage.data.set("empty", None)

    assert storage.data.has("empty") is True
    assert storage.data.get("empty", "default") is None


def test_a_value_is_replaced_and_deleted(storage: AppStorage) -> None:
    storage.data.set("n", 1)
    storage.data.set("n", 2)

    assert storage.data.get("n") == 2
    assert storage.data.delete("n") is True
    assert storage.data.delete("n") is False


def test_settings_and_data_are_separate(storage: AppStorage) -> None:
    storage.settings.set("theme", "dark")
    storage.data.set("theme", "cached")

    assert storage.settings.get("theme") == "dark"
    assert storage.data.get("theme") == "cached"
    assert storage.data.clear() == 1
    assert storage.settings.get("theme") == "dark"


def test_keys_and_items_filter_by_prefix(storage: AppStorage) -> None:
    for key in ("a.one", "a.two", "b.one", "a_x", "axy"):
        storage.data.set(key, key.upper())

    assert storage.data.keys() == sorted(["a.one", "a.two", "b.one", "a_x", "axy"])
    assert storage.data.keys("a.") == ["a.one", "a.two"]
    assert storage.data.keys("a_") == ["a_x"]  # an underscore is not a wildcard
    assert storage.data.keys("a%") == []  # nor is a percent sign
    assert storage.data.items("b.") == {"b.one": "B.ONE"}


@pytest.mark.parametrize("key", ["", " ", "-a", ".a", "a b", "a\\b", "x" * 201, "a\0"])
def test_bad_keys_are_refused(storage: AppStorage, key: str) -> None:
    with pytest.raises(ValueError, match="keys start with"):
        storage.data.set(key, 1)
    with pytest.raises(ValueError, match="keys start with"):
        storage.data.get(key)


def test_a_key_must_be_text(storage: AppStorage) -> None:
    with pytest.raises(ValueError, match="keys start with"):
        storage.data.get(5)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [object(), {1, 2}, float("nan"), float("inf")])
def test_values_that_are_not_json_are_refused(storage: AppStorage, value: Any) -> None:
    with pytest.raises(ValueError, match="not JSON-compatible"):
        storage.data.set("bad", value)


def test_a_huge_value_is_refused(storage: AppStorage) -> None:
    with pytest.raises(ValueError, match="larger than"):
        storage.data.set("big", "x" * MAX_VALUE_BYTES)


def test_values_survive_a_new_object(storage: AppStorage) -> None:
    storage.settings.set("theme", "dark")

    assert AppStorage("notes").settings.get("theme") == "dark"
    assert AppStorage("other").settings.get("theme") is None


def test_the_database_is_created_in_the_app_folder(storage: AppStorage, local_data: Path) -> None:
    storage.data.set("k", 1)

    assert storage.path == local_data / "ColdSoft Technologies" / "Cornea" / "notes" / "app.db"
    assert storage.path.is_file()
    with sqlite3.connect(storage.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_nothing_is_created_until_used(local_data: Path) -> None:
    AppStorage("lazy").data  # noqa: B018

    assert not (AppData.root() / "lazy" / "app.db").exists()


def test_threads_can_write_at_once(storage: AppStorage) -> None:
    def work(n: int) -> None:
        for i in range(20):
            storage.data.set(f"t{n}.{i}", i)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(storage.data.keys("t")) == 120


def test_a_file_that_is_not_a_database_is_set_aside(local_data: Path) -> None:
    path = AppData.database_path("notes")
    path.write_text("this is not sqlite" * 50, encoding="utf-8")

    storage = AppStorage("notes")
    storage.data.set("k", 1)

    assert storage.data.get("k") == 1
    assert len(list(path.parent.glob("app.db.corrupt-*"))) == 1


def test_a_database_from_a_newer_version_is_not_touched(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(StorageError, match="newer Cornea"):
        Database(path).get("settings", "k")
    assert path.is_file()


def test_an_unreadable_value_reads_as_missing(storage: AppStorage) -> None:
    storage.data.set("k", 1)
    with sqlite3.connect(storage.path) as connection:
        connection.execute("UPDATE entries SET value = 'not json' WHERE key = 'k'")

    assert storage.data.get("k", "fallback") == "fallback"


# ----- secrets --------------------------------------------------------------------------------


def test_secrets_are_kept_by_key(storage: AppStorage) -> None:
    storage.secrets.set("token", "s3cret")

    assert storage.secrets.get("token") == "s3cret"
    assert storage.secrets.has("token")
    assert storage.secrets.keys() == ["token"]
    assert storage.secrets.delete("token") is True
    assert storage.secrets.delete("token") is False
    assert storage.secrets.get("token", "none") == "none"


def test_secrets_are_never_written_to_the_database(storage: AppStorage) -> None:
    storage.secrets.set("token", "very-secret-value")
    storage.data.set("k", 1)

    assert b"very-secret-value" not in storage.path.read_bytes()


def test_apps_do_not_see_each_others_secrets() -> None:
    backend = MemoryCredentials()
    SecretStore("one", backend).set("token", "a")
    SecretStore("two", backend).set("token", "b")

    assert SecretStore("one", backend).get("token") == "a"
    assert SecretStore("one", backend).keys() == ["token"]
    assert sorted(backend.entries) == ["Cornea/one/token", "Cornea/two/token"]


@pytest.mark.parametrize("value", ["", None, 5, b"bytes"])
def test_a_secret_must_be_text(value: Any) -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        SecretStore("one", MemoryCredentials()).set("token", value)


def test_a_secret_has_a_size_limit() -> None:
    secrets = SecretStore("one", MemoryCredentials())
    secrets.set("ok", "x" * MAX_SECRET_BYTES)

    with pytest.raises(ValueError, match="at most"):
        secrets.set("big", "x" * (MAX_SECRET_BYTES + 1))
    with pytest.raises(ValueError, match="at most"):
        secrets.set("wide", "é" * MAX_SECRET_BYTES)  # two bytes each


def test_secret_keys_are_checked() -> None:
    with pytest.raises(ValueError, match="keys start with"):
        SecretStore("one", MemoryCredentials()).get("bad key")


@pytest.mark.skipif(sys.platform == "win32", reason="Credential Manager exists here")
def test_secrets_are_unavailable_off_windows() -> None:
    with pytest.raises(SecretsUnavailable, match="only works on Windows"):
        WindowsCredentialBackend()
    with pytest.raises(SecretsUnavailable):
        SecretStore("one").get("token")


# ----- an older version's folder --------------------------------------------------------------


def legacy_file(local_data: Path, app_id: str = "notes") -> Path:
    folder = local_data / "Cornea" / app_id
    folder.mkdir(parents=True)
    return folder / "window.json"


def test_the_old_window_file_is_brought_in_once(local_data: Path) -> None:
    old = legacy_file(local_data)
    old.write_text(json.dumps({"width": 900, "height": 600, "x": 5, "y": 6}), encoding="utf-8")

    storage = AppStorage("notes")

    assert storage.window.get("place") == {"width": 900, "height": 600, "x": 5, "y": 6}
    assert not old.exists()
    assert old.with_name("window.json.migrated").is_file()


def test_the_import_does_not_overwrite_a_newer_place(local_data: Path) -> None:
    AppStorage("notes").window.set("place", {"width": 1, "height": 2})
    old = legacy_file(local_data)
    old.write_text(json.dumps({"width": 900, "height": 600}), encoding="utf-8")

    assert AppStorage("notes").window.get("place") == {"width": 1, "height": 2}
    assert old.exists()


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_a_damaged_old_file_is_left_alone(local_data: Path, content: str) -> None:
    old = legacy_file(local_data)
    old.write_text(content, encoding="utf-8")

    assert AppStorage("notes").window.get("place") is None
    assert old.read_text(encoding="utf-8") == content


def test_no_old_folder_is_fine() -> None:
    assert AppStorage("notes").window.get("place") is None


# ----- the Python API on the shell ------------------------------------------------------------


def test_the_shell_offers_settings_storage_and_secrets() -> None:
    shell = Shell(window=None, identity=App(id="notes"))
    shell._app_storage.secrets._backend = MemoryCredentials()  # type: ignore[union-attr]

    shell.settings.set("theme", "dark")
    shell.storage.set("count", 3)
    shell.secrets.set("token", "t")

    assert (shell.settings.get("theme"), shell.storage.get("count")) == ("dark", 3)
    assert shell.secrets.get("token") == "t"
    assert shell.settings.get("count") is None


@pytest.mark.parametrize("name", ["settings", "storage", "secrets"])
def test_they_need_an_app_id(name: str) -> None:
    shell = Shell(window=None)

    with pytest.raises(RuntimeError, match="need App"):
        getattr(shell, name)


@pytest.mark.parametrize("flag", ["storage", "secrets"])
def test_the_page_flags_need_an_app_id(flag: str) -> None:
    with pytest.raises(ValueError, match="need an app id"):
        Shell(window=None, bridge=Bridge(**{flag: True}))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="need an app id"):
        create_app(bridge=Bridge(**{flag: True}))  # type: ignore[arg-type]


# ----- what the page may call -----------------------------------------------------------------


def invoke(registry: ActionRegistry, name: str, **arguments: Any) -> tuple[int, dict[str, Any]]:
    return asyncio.run(registry.invoke(name, arguments, None))


def registry_for(storage: AppStorage, *, data: bool, secrets: bool) -> ActionRegistry:
    return ActionRegistry(storage=storage, page_storage=data, page_secrets=secrets)


def test_the_page_has_no_storage_by_default(storage: AppStorage) -> None:
    registry = ActionRegistry(storage=storage)

    assert not [name for name in registry.names() if name.startswith(("storage_", "secret_"))]
    assert invoke(registry, "storage_get", key="k")[0] == 404
    assert invoke(registry, "secret_get", key="k")[0] == 404


def test_each_flag_adds_only_its_own_actions(storage: AppStorage) -> None:
    data = registry_for(storage, data=True, secrets=False).names()
    secrets = registry_for(storage, data=False, secrets=True).names()

    assert {n for n in data if n.startswith(("storage_", "secret_"))} == {
        "storage_get",
        "storage_set",
        "storage_delete",
        "storage_keys",
    }
    assert {n for n in secrets if n.startswith(("storage_", "secret_"))} == {
        "secret_get",
        "secret_set",
        "secret_delete",
        "secret_keys",
    }


def test_the_page_reads_and_writes_data(storage: AppStorage) -> None:
    registry = registry_for(storage, data=True, secrets=False)

    assert invoke(registry, "storage_set", key="k", value={"a": [1]}) == (
        200,
        {"available": True, "result": {"stored": True}},
    )
    assert invoke(registry, "storage_get", key="k")[1]["result"] == {"a": [1]}
    assert invoke(registry, "storage_get", key="nope", default=5)[1]["result"] == 5
    assert invoke(registry, "storage_keys")[1]["result"] == ["k"]
    assert invoke(registry, "storage_delete", key="k")[1]["result"] == {"deleted": True}
    assert storage.data.get("k") is None


def test_the_page_can_use_settings_but_not_cornea_namespaces(storage: AppStorage) -> None:
    registry = registry_for(storage, data=True, secrets=False)

    invoke(registry, "storage_set", key="theme", value="dark", area="settings")

    assert storage.settings.get("theme") == "dark"
    assert storage.data.get("theme") is None
    status, body = invoke(registry, "storage_get", key="place", area="cornea.window")
    assert status == 422
    assert "area must be" in body["error"]


@pytest.mark.parametrize(
    ("action", "arguments"),
    [
        ("storage_set", {"key": "bad key", "value": 1}),
        ("storage_get", {"key": ""}),
        ("storage_set", {"key": "k"}),
        ("storage_set", {"key": "k", "value": "x" * MAX_VALUE_BYTES}),
    ],
)
def test_bad_page_calls_are_422(
    storage: AppStorage, action: str, arguments: dict[str, Any]
) -> None:
    assert invoke(registry_for(storage, data=True, secrets=False), action, **arguments)[0] == 422


def test_the_page_reads_and_writes_secrets(storage: AppStorage) -> None:
    registry = registry_for(storage, data=False, secrets=True)

    assert invoke(registry, "secret_set", key="token", value="abc")[1]["result"] == {"stored": True}
    assert invoke(registry, "secret_get", key="token")[1]["result"] == "abc"
    assert invoke(registry, "secret_keys")[1]["result"] == ["token"]
    assert invoke(registry, "secret_delete", key="token")[1]["result"] == {"deleted": True}
    assert invoke(registry, "secret_get", key="token", default="d")[1]["result"] == "d"


def test_secrets_off_windows_are_unavailable_not_an_error() -> None:
    if sys.platform == "win32":
        pytest.skip("Credential Manager exists here")
    registry = registry_for(AppStorage("notes"), data=False, secrets=True)

    status, body = invoke(registry, "secret_get", key="token")

    assert status == 200
    assert body["available"] is False
    assert "Windows" in body["reason"]


def test_storage_actions_can_be_disabled_and_not_replaced(storage: AppStorage) -> None:
    registry = ActionRegistry(
        ("secret_get",), storage=storage, page_storage=True, page_secrets=True
    )

    assert "secret_get" not in registry.names()
    assert "secret_set" in registry.names()
    with pytest.raises(ValueError, match="built-in"):
        registry.register("storage_get", lambda: None)


def test_the_app_factory_hands_the_page_the_apps_storage() -> None:
    app = create_app(bridge=Bridge(storage=True), app_id="notes")

    assert "storage_get" in app.state.actions.names()
    assert isinstance(app.state.storage, AppStorage)


# ----- Credential Manager's calls, against a stand-in for advapi32 ----------------------------


class FakeFunction:
    """One advapi32 function: ctypes sets ``argtypes`` on it and then calls it."""

    def __init__(self, action: Any) -> None:
        self.action = action
        self.argtypes: Any = None

    def __call__(self, *args: Any) -> int:
        return int(self.action(*args))


class FakeAdvapi:
    """Keeps credentials the way Credential Manager would, and fails on demand."""

    def __init__(self) -> None:
        self.vault: dict[str, Any] = {}
        self.error = 0
        self.CredReadW = FakeFunction(self.read)
        self.CredWriteW = FakeFunction(self.write)
        self.CredDeleteW = FakeFunction(self.delete)
        self.CredEnumerateW = FakeFunction(self.enumerate)
        self.CredFree = FakeFunction(lambda pointer: 1)
        self.kept: list[Any] = []

    def read(self, target: str, kind: int, flags: int, out: Any) -> bool:
        if target not in self.vault:
            self.error = 1168
            return False
        out._obj.contents = self.vault[target]
        return True

    def write(self, credential: Any, flags: int) -> bool:
        if self.error == -1:
            self.error = 5
            return False
        source = credential._obj
        copy = type(source)()
        data = ctypes.string_at(source.CredentialBlob, source.CredentialBlobSize)
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        self.kept.append(buffer)
        copy.TargetName = source.TargetName
        copy.CredentialBlobSize = source.CredentialBlobSize
        copy.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        assert (source.Type, source.Persist, source.UserName) == (1, 2, "cornea")
        self.vault[source.TargetName] = copy
        return True

    def delete(self, target: str, kind: int, flags: int) -> bool:
        if self.vault.pop(target, None) is None:
            self.error = 1168
            return False
        return True

    def enumerate(self, pattern: str, flags: int, count: Any, out: Any) -> bool:
        found = [c for name, c in self.vault.items() if name.startswith(pattern.rstrip("*"))]
        if not found:
            self.error = 1168
            return False
        pointer = ctypes.POINTER(type(found[0]))
        array = (pointer * len(found))(*[ctypes.pointer(c) for c in found])
        self.kept.append(array)
        count._obj.value = len(found)
        out._obj.contents = array[0]
        return True


@pytest.fixture
def advapi(monkeypatch: pytest.MonkeyPatch) -> FakeAdvapi:
    fake = FakeAdvapi()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, use_last_error=False: fake, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: fake.error, raising=False)
    monkeypatch.setattr(ctypes, "WinError", lambda code: OSError(f"error {code}"), raising=False)
    return fake


def test_windows_backend_reads_writes_lists_and_deletes(advapi: FakeAdvapi) -> None:
    secrets = SecretStore("notes", WindowsCredentialBackend())

    secrets.set("token", "pä55 ☃")
    secrets.set("other", "x")

    assert secrets.get("token") == "pä55 ☃"
    assert secrets.keys() == ["other", "token"]
    assert sorted(advapi.vault) == ["Cornea/notes/other", "Cornea/notes/token"]
    assert secrets.delete("token") is True
    assert secrets.delete("token") is False
    assert secrets.get("token", "none") == "none"


def test_windows_backend_with_nothing_stored_is_empty(advapi: FakeAdvapi) -> None:
    secrets = SecretStore("notes", WindowsCredentialBackend())

    assert secrets.keys() == []
    assert secrets.get("token") is None


def test_windows_backend_reports_a_failed_write(advapi: FakeAdvapi) -> None:
    advapi.error = -1

    with pytest.raises(SecretsUnavailable, match="could not write"):
        SecretStore("notes", WindowsCredentialBackend()).set("token", "x")
