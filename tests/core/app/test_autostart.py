"""Starting an app at login through the per-user Run key."""

import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from cornea import App, Autostart, AutostartStatus, Shell
from cornea.core.app import autostart as autostart_module


class FakeKey:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def __enter__(self) -> "FakeKey":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def make_winreg(values: dict[str, str], opened: list[Any]) -> ModuleType:
    module = ModuleType("winreg")
    module.HKEY_CURRENT_USER = "HKCU"  # type: ignore[attr-defined]
    module.KEY_SET_VALUE = 2  # type: ignore[attr-defined]
    module.KEY_READ = 1  # type: ignore[attr-defined]
    module.REG_SZ = 1  # type: ignore[attr-defined]

    def create(hive: str, path: str, reserved: int, access: int) -> FakeKey:
        opened.append((hive, path))
        return FakeKey(values)

    def open_key(hive: str, path: str, reserved: int, access: int) -> FakeKey:
        opened.append((hive, path))
        return FakeKey(values)

    def set_value(key: FakeKey, name: str, reserved: int, kind: int, value: str) -> None:
        key.values[name] = value

    def delete(key: FakeKey, name: str) -> None:
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]

    def query(key: FakeKey, name: str) -> tuple[str, int]:
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name], 1

    module.CreateKeyEx = create  # type: ignore[attr-defined]
    module.OpenKey = open_key  # type: ignore[attr-defined]
    module.SetValueEx = set_value  # type: ignore[attr-defined]
    module.DeleteValue = delete  # type: ignore[attr-defined]
    module.QueryValueEx = query  # type: ignore[attr-defined]
    return module


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    values: dict[str, str] = {"Other": "other.exe"}
    opened: list[Any] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", make_winreg(values, opened))
    return SimpleNamespace(values=values, opened=opened)


def test_it_is_off_until_enabled(registry: SimpleNamespace) -> None:
    autostart = Autostart("com.example.notes")

    assert autostart.status() == AutostartStatus(enabled=False)
    assert autostart.enabled is False


def test_enable_writes_the_per_user_run_key(registry: SimpleNamespace) -> None:
    status = Autostart("com.example.notes").enable("C:\\Apps\\notes.exe --minimized")

    assert registry.values["com.example.notes"] == "C:\\Apps\\notes.exe --minimized"
    assert registry.values["Other"] == "other.exe"
    assert ("HKCU", autostart_module.RUN_KEY) in registry.opened
    assert status.enabled
    assert status.command == "C:\\Apps\\notes.exe --minimized"
    assert status.current is False


def test_the_default_command_starts_this_program(
    registry: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["main.py", "--flag"])
    autostart = Autostart("app")

    status = autostart.enable()

    assert status.current is True
    assert status.command == Autostart.default_command()
    assert "main.py" in status.command
    assert "--flag" in status.command


def test_enabling_again_replaces_the_entry(registry: SimpleNamespace) -> None:
    autostart = Autostart("app")
    autostart.enable("old.exe")

    autostart.enable("new.exe")

    assert registry.values["app"] == "new.exe"


def test_disable_removes_only_this_entry(registry: SimpleNamespace) -> None:
    autostart = Autostart("app")
    autostart.enable("app.exe")

    assert autostart.disable() is True
    assert autostart.disable() is False
    assert registry.values == {"Other": "other.exe"}


@pytest.mark.parametrize("command", ["", "   ", "a\nb", "a\0b", "x" * 3000, 5])
def test_bad_commands_are_refused(registry: SimpleNamespace, command: Any) -> None:
    with pytest.raises(ValueError, match="command"):
        Autostart("app").enable(command)

    assert "app" not in registry.values


def test_the_shell_needs_an_app_id() -> None:
    with pytest.raises(ValueError, match="app id"):
        _ = Shell(window=None).autostart


def test_the_shell_uses_the_app_id(registry: SimpleNamespace) -> None:
    shell = Shell(window=None, identity=App(id="com.example.notes"))

    shell.autostart.enable("notes.exe")

    assert registry.values["com.example.notes"] == "notes.exe"
    assert shell.autostart.status().enabled


@pytest.mark.skipif(sys.platform == "win32", reason="checks other systems")
def test_other_systems_say_so() -> None:
    for call in (Autostart("app").status, Autostart("app").disable, Autostart("app").enable):
        with pytest.raises(RuntimeError, match="only works on Windows"):
            call()
