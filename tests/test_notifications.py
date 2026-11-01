"""Windows toast notifications, with the Windows runtime stood in by fakes."""

import asyncio
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from cornea import Bridge, Shell, Static, Window
from cornea.core import notifications as notifications_module
from cornea.core.bridge import ActionRegistry, invoke_action
from cornea.core.notifications import Notifier, check_notification, toast_xml
from cornea.core.window import NativeWindow, Unavailable, create_native_window
from test_window import FakeWebview, FakeWindow


class FakeXml:
    def __init__(self) -> None:
        self.text = ""

    def load_xml(self, text: str) -> None:
        self.text = text


class FakeToast:
    def __init__(self, document: FakeXml) -> None:
        self.document = document
        self.handlers: dict[str, Any] = {}

    def add_activated(self, handler: Any) -> None:
        self.handlers["activated"] = handler

    def add_dismissed(self, handler: Any) -> None:
        self.handlers["dismissed"] = handler

    def add_failed(self, handler: Any) -> None:
        self.handlers["failed"] = handler


class Shown:
    """What the fake Windows runtime was asked to show."""

    def __init__(self) -> None:
        self.toasts: list[FakeToast] = []
        self.identities: list[str] = []


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> Shown:
    shown = Shown()

    class Manager:
        @staticmethod
        def create_toast_notifier_with_id(app_id: str) -> Any:
            shown.identities.append(app_id)

            class Notifier_:
                @staticmethod
                def show(toast: FakeToast) -> None:
                    shown.toasts.append(toast)

            return Notifier_

    dom = ModuleType("winrt.windows.data.xml.dom")
    dom.XmlDocument = FakeXml  # type: ignore[attr-defined]
    notifications = ModuleType("winrt.windows.ui.notifications")
    notifications.ToastNotification = FakeToast  # type: ignore[attr-defined]
    notifications.ToastNotificationManager = Manager  # type: ignore[attr-defined]
    for name, module in (
        ("winrt", ModuleType("winrt")),
        ("winrt.windows", ModuleType("winrt.windows")),
        ("winrt.windows.data", ModuleType("winrt.windows.data")),
        ("winrt.windows.data.xml", ModuleType("winrt.windows.data.xml")),
        ("winrt.windows.data.xml.dom", dom),
        ("winrt.windows.ui", ModuleType("winrt.windows.ui")),
        ("winrt.windows.ui.notifications", notifications),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(Notifier, "_register", lambda self: None)
    notifications_module._alive.clear()
    return shown


# ----- what is allowed --------------------------------------------------------------------------


def test_the_text_is_escaped_so_it_cannot_add_markup() -> None:
    xml = toast_xml("A <b>&", "x </text><actions>")

    assert "<b>" not in xml
    assert "&lt;b&gt;&amp;" in xml
    assert "</text><actions>" not in xml


@pytest.mark.parametrize(
    ("title", "message", "identifier", "problem"),
    [
        ("", "m", None, "title must be"),
        (5, "m", None, "title must be"),
        ("t" * 65, "m", None, "at most 64"),
        ("t", " ", None, "message must be"),
        ("t", "m" * 257, None, "at most 256"),
        ("t", "m", "has space", "notification_id must be"),
        ("t", "m", 5, "notification_id must be"),
    ],
)
def test_bad_input_is_refused(title: Any, message: Any, identifier: Any, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        check_notification(title, message, identifier)


def test_a_good_notification_passes() -> None:
    check_notification("Done", "The export finished.", "export-1")


# ----- showing ----------------------------------------------------------------------------------


def test_a_toast_is_shown_under_the_apps_identity(
    windows: Shown, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    Notifier("com.example.notes", "Notes").show("Saved", "All changes saved.")

    assert windows.identities == ["com.example.notes"]
    assert "<text>Saved</text>" in windows.toasts[0].document.text


def test_without_an_app_id_the_default_identity_is_used(
    windows: Shown, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    Notifier(None, "Notes").show("Saved", "All changes saved.")

    assert windows.identities == ["Cornea.Shell"]


def test_a_click_runs_the_callback_once_and_frees_the_toast(
    windows: Shown, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    clicks: list[str] = []

    Notifier(None, "Notes").show("Saved", "Done.", lambda: clicks.append("click"))
    toast = windows.toasts[0]
    assert toast in notifications_module._alive
    toast.handlers["activated"](None, None)

    assert clicks == ["click"]
    assert toast not in notifications_module._alive


def test_a_failing_click_handler_is_logged_not_raised(
    windows: Shown, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    def broken() -> None:
        raise RuntimeError("bug")

    Notifier(None, "Notes").show("Saved", "Done.", broken)

    windows.toasts[0].handlers["activated"](None, None)  # must not raise


def test_a_dismissed_toast_is_freed(windows: Shown, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    Notifier(None, "Notes").show("Saved", "Done.")
    windows.toasts[0].handlers["dismissed"](None, None)

    assert not notifications_module._alive


def test_other_systems_say_it_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(Unavailable, match="only work on Windows"):
        Notifier(None, "Notes").show("Saved", "Done.")


def test_a_missing_extra_says_how_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winrt.windows.data.xml.dom", None)

    with pytest.raises(Unavailable, match=r"cornea-shell\[notifications\]"):
        Notifier(None, "Notes").show("Saved", "Done.")


def test_the_identity_is_registered_with_the_title_and_icon(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    written: dict[str, str] = {}
    keys: list[str] = []

    class Key:
        def __enter__(self) -> "Key":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    import winreg

    def create_key(root: int, path: str) -> Key:
        keys.append(path)
        return Key()

    monkeypatch.setattr(winreg, "CreateKey", create_key)
    monkeypatch.setattr(
        winreg, "SetValueEx", lambda key, name, reserved, kind, value: written.update({name: value})
    )
    icon = tmp_path / "icon.png"

    Notifier("com.example.notes", "Notes", icon)._register()

    assert keys == [r"Software\Classes\AppUserModelId\com.example.notes"]
    assert written == {"DisplayName": "Notes", "IconUri": str(icon.resolve())}


# ----- the window, the action and the shell -----------------------------------------------------


@pytest.fixture
def webview(monkeypatch: pytest.MonkeyPatch) -> FakeWebview:
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    return fake


def make(webview: FakeWebview) -> tuple[FakeWindow, NativeWindow, list[str]]:
    scripts: list[str] = []
    window, controller = create_native_window(webview, "http://x", Window(), lambda error: None)
    window.evaluate_js = lambda script: scripts.append(script)
    window.show = lambda: None
    return window, controller, scripts


def test_a_click_activates_the_window_and_tells_the_page(
    webview: FakeWebview, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, controller, scripts = make(webview)
    monkeypatch.setattr("cornea.core.window.bring_to_front", lambda window: None)
    shown: list[Any] = []

    class Recording:
        def show(self, title: str, message: str, on_click: Any) -> None:
            shown.append((title, message))
            on_click()

    controller.notifier = Recording()  # type: ignore[assignment]

    controller.show_notification("Done", "Export finished.", "export-1")

    assert shown == [("Done", "Export finished.")]
    assert 'new CustomEvent("cornea:notification-click"' in scripts[0]
    assert '{"id": "export-1"}' in scripts[0]


def test_without_a_notifier_the_window_says_it_is_unavailable(webview: FakeWebview) -> None:
    _, controller, _ = make(webview)

    with pytest.raises(Unavailable):
        controller.show_notification("Done", "Export finished.")


def run(registry: ActionRegistry, arguments: dict[str, Any], window: Any = None) -> tuple[int, Any]:
    return asyncio.run(invoke_action(registry, "show_notification", arguments, window))


def test_the_action_is_off_by_default() -> None:
    assert "show_notification" not in ActionRegistry().names()
    assert "show_notification" in ActionRegistry(notifications=True).names()


def test_the_action_asks_the_window_for_a_toast() -> None:
    calls: list[Any] = []

    class FakeController:
        headless = False

        def show_notification(self, *args: Any) -> None:
            calls.append(args)

    status, body = run(
        ActionRegistry(notifications=True),
        {"title": "Done", "message": "Finished.", "notification_id": "a1"},
        FakeController(),
    )

    assert (status, body["result"]) == (200, {"shown": True})
    assert calls == [("Done", "Finished.", "a1")]


def test_the_action_checks_its_arguments() -> None:
    status, body = run(ActionRegistry(notifications=True), {"title": "", "message": "x"}, object())

    assert status == 422
    assert "title" in body["error"]


def test_the_action_without_a_window_is_unavailable() -> None:
    status, body = run(ActionRegistry(notifications=True), {"title": "T", "message": "M"})

    assert (status, body["available"]) == (200, False)


def test_a_bridge_setting_turns_the_action_on(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")

    shell = Shell(Static(tmp_path), window=None, bridge=Bridge(notifications=True))

    assert "show_notification" in shell.actions.names()


def test_the_shell_can_always_show_one_from_python(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    shell = Shell(Static(tmp_path), window=None)

    with pytest.raises(RuntimeError, match="no window"):
        shell.show_notification("Done", "Finished.")
    with pytest.raises(ValueError, match="title must be"):
        shell.show_notification("", "Finished.")
