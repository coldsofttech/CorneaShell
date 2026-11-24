"""Registering a URL scheme and file types for the current user."""

import sys
from types import ModuleType
from typing import Any

import pytest

from cornea import App, Associations, Shell


class FakeRegistry:
    """A registry tree: key path (lowercase) -> {value name: data}."""

    def __init__(self) -> None:
        self.keys: dict[str, dict[str, str]] = {}


class FakeKey:
    def __init__(self, registry: FakeRegistry, path: str) -> None:
        self.registry, self.path = registry, path

    def __enter__(self) -> "FakeKey":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def make_winreg(registry: FakeRegistry) -> ModuleType:
    module = ModuleType("winreg")
    module.HKEY_CURRENT_USER = "HKCU"  # type: ignore[attr-defined]
    module.KEY_SET_VALUE = 2  # type: ignore[attr-defined]
    module.KEY_READ = 1  # type: ignore[attr-defined]
    module.REG_SZ = 1  # type: ignore[attr-defined]

    def norm(path: str) -> str:
        return path.lower()

    def create(hive: str, path: str, reserved: int, access: int) -> FakeKey:
        parts = norm(path).split("\\")
        for count in range(1, len(parts) + 1):  # like Windows, parents are created too
            registry.keys.setdefault("\\".join(parts[:count]), {})
        return FakeKey(registry, norm(path))

    def open_key(hive: str, path: str, reserved: int, access: int) -> FakeKey:
        if norm(path) not in registry.keys:
            raise FileNotFoundError(path)
        return FakeKey(registry, norm(path))

    def set_value(key: FakeKey, name: str, reserved: int, kind: int, value: str) -> None:
        registry.keys[key.path][name] = value

    def query(key: FakeKey, name: str) -> tuple[str, int]:
        values = registry.keys[key.path]
        if name not in values:
            raise FileNotFoundError(name)
        return values[name], 1

    def delete_value(key: FakeKey, name: str) -> None:
        if name not in registry.keys[key.path]:
            raise FileNotFoundError(name)
        del registry.keys[key.path][name]

    def children(path: str) -> list[str]:
        prefix = norm(path) + "\\"
        return sorted(
            {k[len(prefix) :].split("\\")[0] for k in registry.keys if k.startswith(prefix)}
        )

    def enum_key(key: FakeKey, index: int) -> str:
        names = children(key.path)
        if index >= len(names):
            raise OSError("no more")
        return names[index]

    def delete_key(hive: str, path: str) -> None:
        if children(path):
            raise OSError("key has subkeys")
        registry.keys.pop(norm(path))

    module.CreateKeyEx = create  # type: ignore[attr-defined]
    module.OpenKey = open_key  # type: ignore[attr-defined]
    module.SetValueEx = set_value  # type: ignore[attr-defined]
    module.QueryValueEx = query  # type: ignore[attr-defined]
    module.DeleteValue = delete_value  # type: ignore[attr-defined]
    module.EnumKey = enum_key  # type: ignore[attr-defined]
    module.DeleteKey = delete_key  # type: ignore[attr-defined]
    return module


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> FakeRegistry:
    fake = FakeRegistry()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", make_winreg(fake))
    return fake


COMMAND = '"C:\\Apps\\notes.exe"'


# ----- URL scheme -------------------------------------------------------------------------------


def test_a_scheme_is_registered_for_the_current_user(registry: FakeRegistry) -> None:
    associations = Associations("com.example.notes")

    assert associations.register_protocol("MyApp", command=COMMAND, name="Notes") == "myapp"

    base = r"software\classes\myapp"
    assert registry.keys[base][""] == "URL:Notes"
    assert registry.keys[base]["URL Protocol"] == ""
    assert registry.keys[base + r"\shell\open\command"][""] == COMMAND + ' "%1"'
    assert associations.protocol_command("myapp") == COMMAND + ' "%1"'


def test_the_argument_is_always_quoted(registry: FakeRegistry) -> None:
    Associations("a").register_protocol("myapp", command="C:\\notes.exe --x")

    assert Associations("a").protocol_command("myapp") == 'C:\\notes.exe --x "%1"'


def test_the_default_command_starts_this_program(registry: FakeRegistry) -> None:
    Associations("a").register_protocol("myapp")

    command = Associations("a").protocol_command("myapp")
    assert command is not None
    assert command.endswith(' "%1"')
    assert sys.executable.lower().split("\\")[-1].split("/")[-1][:6] in command.lower()


def test_registering_again_replaces_the_entry(registry: FakeRegistry) -> None:
    associations = Associations("a")
    associations.register_protocol("myapp", command="old.exe")

    associations.register_protocol("myapp", command="new.exe")

    assert associations.protocol_command("myapp") == 'new.exe "%1"'


def test_a_scheme_is_removed_with_everything_under_it(registry: FakeRegistry) -> None:
    associations = Associations("a")
    associations.register_protocol("myapp", command="x.exe")

    assert associations.unregister_protocol("myapp") is True
    assert associations.unregister_protocol("myapp") is False
    assert [key for key in registry.keys if "myapp" in key] == []
    assert associations.protocol_command("myapp") is None


def test_another_programs_scheme_is_never_removed(registry: FakeRegistry) -> None:
    registry.keys[r"software\classes\theirs"] = {"": "URL:Theirs"}
    registry.keys[r"software\classes\theirs\shell\open\command"] = {"": "theirs.exe"}

    assert Associations("a").unregister_protocol("theirs") is False
    assert Associations("b").register_protocol("mine") == "mine"
    assert Associations("a").unregister_protocol("mine") is False  # owned by b

    assert r"software\classes\theirs\shell\open\command" in registry.keys
    assert r"software\classes\mine" in registry.keys


@pytest.mark.parametrize(
    "scheme",
    ["", "a", "1abc", "my app", "my_app", "x" * 40, "http", "HTTPS", "file", "mailto", "javascript",
     "ms-settings", 5, None],
)  # fmt: skip
def test_bad_schemes_are_refused(registry: FakeRegistry, scheme: Any) -> None:
    with pytest.raises(ValueError, match=r"scheme|belongs"):
        Associations("a").register_protocol(scheme)

    assert registry.keys == {}


@pytest.mark.parametrize("name", ["a\nb", "x" * 200, 5])
def test_a_bad_name_is_refused(registry: FakeRegistry, name: Any) -> None:
    with pytest.raises(ValueError, match=r"name"):
        Associations("a").register_protocol("myapp", name=name)


def test_a_bad_command_is_refused(registry: FakeRegistry) -> None:
    with pytest.raises(ValueError, match=r"command"):
        Associations("a").register_protocol("myapp", command="a\0b")

    assert registry.keys == {}


# ----- file types -------------------------------------------------------------------------------


def test_a_file_type_is_added_to_open_with_without_taking_the_default(
    registry: FakeRegistry,
) -> None:
    registry.keys[r"software\classes\.notes"] = {"": "OtherApp.notes"}
    associations = Associations("com.example.notes")

    assert (
        associations.register_file_type("NOTES", description="Notes file", command=COMMAND)
        == ".notes"
    )

    assert registry.keys[r"software\classes\.notes"][""] == "OtherApp.notes"  # untouched
    assert registry.keys[r"software\classes\.notes\openwithprogids"] == {
        "com.example.notes.notes": ""
    }
    prog = r"software\classes\com.example.notes.notes"
    assert registry.keys[prog][""] == "Notes file"
    assert registry.keys[prog + r"\shell\open\command"][""] == COMMAND + ' "%1"'
    assert associations.file_type_command(".notes") == COMMAND + ' "%1"'


def test_a_file_type_is_removed_again(registry: FakeRegistry) -> None:
    associations = Associations("a")
    associations.register_file_type(".notes", command="x.exe")

    assert associations.unregister_file_type(".notes") is True
    assert associations.unregister_file_type(".notes") is False
    assert associations.file_type_command(".notes") is None
    assert registry.keys[r"software\classes\.notes\openwithprogids"] == {}


def test_another_apps_file_entry_is_left_alone(registry: FakeRegistry) -> None:
    Associations("b").register_file_type(".notes", command="b.exe")

    assert Associations("a").unregister_file_type(".notes") is False
    assert Associations("b").file_type_command(".notes") == 'b.exe "%1"'


@pytest.mark.parametrize(
    "extension",
    [".exe", "BAT", ".ps1", ".lnk", ".js", ".reg", ".dll", ".", "", "..a", ".a b", ".x" * 20, 5],
)
def test_programs_and_odd_extensions_are_refused(registry: FakeRegistry, extension: Any) -> None:
    with pytest.raises(ValueError, match=r"extension|cannot be claimed"):
        Associations("a").register_file_type(extension)

    assert registry.keys == {}


def test_a_missing_dot_is_added(registry: FakeRegistry) -> None:
    assert Associations("a").register_file_type("md") == ".md"


# ----- the shell and other systems --------------------------------------------------------------


def test_the_shell_needs_an_app_id() -> None:
    with pytest.raises(ValueError, match="app id"):
        _ = Shell(window=None).associations


def test_the_shell_uses_the_app_id(registry: FakeRegistry) -> None:
    shell = Shell(window=None, identity=App(id="com.example.notes"))

    shell.associations.register_protocol("notes", command="n.exe")

    assert registry.keys[r"software\classes\notes"]["CorneaApp"] == "com.example.notes"


@pytest.mark.skipif(sys.platform == "win32", reason="checks other systems")
def test_other_systems_say_so() -> None:
    associations = Associations("a")
    for call in (
        lambda: associations.register_protocol("myapp"),
        lambda: associations.unregister_protocol("myapp"),
        lambda: associations.register_file_type(".notes"),
        lambda: associations.file_type_command(".notes"),
    ):
        with pytest.raises(RuntimeError, match="only work on Windows"):
            call()
