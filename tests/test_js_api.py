"""The opt-in window.pywebview.api object."""

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cornea import Shell, Static, Url, Window
from cornea.core import shell as shell_module
from cornea.core import window as window_module
from cornea.core.bridge import ActionRegistry
from cornea.core.window import SimulatedWindow, create_native_window
from cornea.core.window_api import WindowApi
from test_window import FakeWebview


class Recorder:
    """A window controller that remembers what it was asked."""

    headless = False

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def minimize(self) -> None:
        self.calls.append(("minimize", None))

    def maximize(self) -> None:
        self.calls.append(("maximize", None))

    def restore(self) -> None:
        self.calls.append(("restore", None))

    def close(self) -> None:
        self.calls.append(("close", None))

    def set_title(self, title: str) -> None:
        self.calls.append(("set_title", title))

    def state(self) -> dict[str, Any]:
        return {"title": "T", "maximized": False}

    def dialog(self, kind: str, **options: Any) -> list[str] | None:
        self.calls.append((f"dialog:{kind}", options))
        return ["C:/chosen"]


def make_api() -> tuple[WindowApi, Recorder]:
    api = WindowApi(ActionRegistry())
    controller = Recorder()
    api._controller = controller
    return api, controller


# ----- the object -----------------------------------------------------------------------------


def test_the_controls_reach_the_window() -> None:
    api, controller = make_api()

    results = [api.minimize(), api.maximize(), api.restore(), api.close()]
    api.set_title("New")

    assert results == [{"ok": True}] * 4
    assert controller.calls == [
        ("minimize", None),
        ("maximize", None),
        ("restore", None),
        ("close", None),
        ("set_title", "New"),
    ]


def test_the_state_is_the_windows() -> None:
    api, _ = make_api()

    assert api.state() == {"title": "T", "maximized": False}


@pytest.mark.parametrize("title", ["", "x" * 201, 5])
def test_a_bad_title_is_refused(title: Any) -> None:
    api, controller = make_api()

    with pytest.raises(ValueError, match="title must be"):
        api.set_title(title)

    assert controller.calls == []


def test_the_native_actions_are_listed_and_called() -> None:
    api, controller = make_api()

    assert "platform_info" in api.actions()
    answer = api.call_action("choose_folder", {"directory": "C:/"})

    assert answer == {"available": True, "result": "C:/chosen"}
    assert controller.calls == [("dialog:folder", {"directory": "C:/"})]


def test_actions_answer_like_the_http_route() -> None:
    api, _ = make_api()

    assert api.call_action("no_such_action") == {"error": "Unknown action"}
    assert api.call_action("open_external", {"url": "file:///etc/passwd"})["error"].startswith(
        "only http"
    )
    assert "error" in api.call_action("choose_folder", {"bogus": 1})


def test_the_hosts_own_actions_can_be_called() -> None:
    registry = ActionRegistry()
    registry.register("double", lambda number: number * 2)
    api = WindowApi(registry)
    api._controller = Recorder()

    assert api.call_action("double", {"number": 4}) == {"available": True, "result": 8}
    assert "double" in api.actions()


def test_switched_off_actions_cannot_be_called() -> None:
    api = WindowApi(ActionRegistry(disabled=("open_external",)))
    api._controller = Recorder()

    assert api.call_action("open_external", {"url": "https://example.com"}) == {
        "error": "Unknown action"
    }


def test_dialogs_without_a_window_are_unavailable() -> None:
    api = WindowApi(ActionRegistry())
    api._controller = SimulatedWindow("t")

    answer = api.call_action("choose_file")

    assert answer["available"] is False


def test_nothing_works_before_the_window_exists() -> None:
    api = WindowApi(ActionRegistry())

    with pytest.raises(RuntimeError, match="not ready"):
        api.minimize()


def test_only_the_intended_names_are_public() -> None:
    """pywebview exposes every public attribute to the page, so keep that list short."""
    public = {name for name in dir(WindowApi) if not name.startswith("_")}

    assert public == {
        "actions",
        "call_action",
        "close",
        "maximize",
        "minimize",
        "restore",
        "set_title",
        "state",
    }
    api = WindowApi(ActionRegistry())
    assert {name for name in vars(api) if not name.startswith("_")} == set()


# ----- creating the window --------------------------------------------------------------------


def test_the_api_is_given_to_the_window_only_when_asked() -> None:
    webview = FakeWebview()

    plain, _ = create_native_window(webview, "http://x", Window(), lambda error: None)
    trusted, controller = create_native_window(
        webview, "http://x", Window(js_api=True), lambda error: None
    )

    assert "js_api" not in plain.options
    assert isinstance(trusted.options["js_api"], WindowApi)
    assert trusted.options["js_api"]._controller is controller


def test_the_api_uses_the_shells_actions() -> None:
    webview = FakeWebview()
    registry = ActionRegistry()
    registry.register("ping", lambda: "pong")

    window, _ = create_native_window(
        webview, "http://x", Window(js_api=True), lambda error: None, None, None, registry
    )

    assert window.options["js_api"].call_action("ping") == {"available": True, "result": "pong"}


# ----- direct addresses -----------------------------------------------------------------------


def test_a_frameless_direct_address_is_refused_without_the_api() -> None:
    with pytest.raises(ValueError, match="js_api=True"):
        Shell(Url("http://localhost:5173"), window=Window(frameless=True))


def test_a_frameless_direct_address_is_allowed_with_the_api() -> None:
    shell = Shell(Url("http://localhost:5173"), window=Window(frameless=True, js_api=True))

    assert shell.is_direct


def test_the_shell_hands_its_actions_to_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(window_module, "_registry_version", lambda: "1")
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace())

    def create(*args: Any) -> Any:
        seen["actions"] = args[-1]
        return None, SimpleNamespace()

    monkeypatch.setattr(shell_module, "create_native_window", create)
    monkeypatch.setattr(shell_module, "show_window", lambda *args: None)
    shell = Shell(Static(tmp_path), window=Window(js_api=True))
    shell.action("mine")(lambda: "x")

    shell.run()

    assert seen["actions"] is shell.actions
    assert "mine" in seen["actions"].names()


def test_no_parameter_hides_a_javascript_name() -> None:
    """pywebview writes the page's functions from these names; `arguments` would break them."""
    import inspect

    reserved = {"arguments", "this", "function", "new", "delete", "default", "var", "let"}
    for name in dir(WindowApi):
        if name.startswith("_"):
            continue
        parameters = set(inspect.signature(getattr(WindowApi, name)).parameters) - {"self"}
        assert not parameters & reserved, name
