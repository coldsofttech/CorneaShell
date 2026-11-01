"""Telling the page things, holding the window open, dropped files, and opening files."""

import http.client
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from cornea import Bridge, Shell, Static, Window
from cornea.core import bridge as bridge_module
from cornea.core import window as window_module
from cornea.core.bridge import ActionRegistry, BadArguments, invoke_action
from cornea.core.close_guard import CloseGuard
from cornea.core.window import NativeWindow, Unavailable, create_native_window
from test_window import FakeWebview, FakeWindow


@pytest.fixture
def webview(monkeypatch: pytest.MonkeyPatch) -> FakeWebview:
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(window_module, "CLOSE_DELAY", 0)
    return fake


def make(
    webview: FakeWebview, settings: Window | None = None
) -> tuple[FakeWindow, NativeWindow, list[str]]:
    scripts: list[str] = []
    window, controller = create_native_window(
        webview, "http://x", settings or Window(), lambda error: None
    )
    window.evaluate_js = lambda script: scripts.append(script)
    return window, controller, scripts


# ----- telling the page -------------------------------------------------------------------------


def test_a_notification_is_a_dom_event_with_the_prefix(webview: FakeWebview) -> None:
    _, controller, scripts = make(webview)

    controller.notify("export-done", {"rows": 3})

    assert len(scripts) == 1
    assert 'new CustomEvent("cornea:export-done"' in scripts[0]
    assert '{detail: {"rows": 3}}' in scripts[0]


def test_event_names_are_checked(webview: FakeWebview) -> None:
    _, controller, _ = make(webview)

    with pytest.raises(ValueError, match="event names look like"):
        controller.notify("Bad Name")


def test_a_page_that_is_not_there_is_not_an_error(webview: FakeWebview) -> None:
    window, controller, _ = make(webview)

    def fail(script: str) -> None:
        raise RuntimeError("no page")

    window.evaluate_js = fail  # type: ignore[attr-defined]

    controller.notify("hello")


def test_shell_notify_without_a_window_checks_the_name_and_does_nothing(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    shell = Shell(Static(tmp_path), window=None)

    shell.notify("hello", {"a": 1})

    with pytest.raises(ValueError, match="event names look like"):
        shell.notify("Hello")


# ----- the close guard --------------------------------------------------------------------------


def test_a_guard_holds_the_window_and_tells_the_page(webview: FakeWebview) -> None:
    window, controller, scripts = make(webview)
    guard = CloseGuard()
    guard.add(lambda: True)
    controller.guard = guard

    assert controller.close() is False

    assert "destroy" not in window.calls
    assert "cornea:close-blocked" in scripts[0]


def test_force_closes_a_held_window(webview: FakeWebview) -> None:
    window, controller, _ = make(webview)
    guard = CloseGuard()
    guard.add(lambda: True)
    controller.guard = guard

    assert controller.close(force=True) is True
    assert window.events.closing.handlers[0]() is True  # and the real close is not held again


def test_closing_by_any_other_means_is_held_too(webview: FakeWebview) -> None:
    window, controller, scripts = make(webview)
    guard = CloseGuard()
    guard.page_holds = True
    controller.guard = guard

    results = [handler() for handler in window.events.closing.handlers]

    assert results[0] is False
    assert "cornea:close-blocked" in scripts[0]


def test_without_a_guard_the_window_closes(webview: FakeWebview) -> None:
    window, controller, _ = make(webview)

    assert controller.close() is True
    assert window.events.closing.handlers[0]() is True


def test_a_failing_guard_never_holds_the_window() -> None:
    guard = CloseGuard()

    def broken() -> bool:
        raise RuntimeError("bug")

    guard.add(broken)

    assert guard.holds() is False


def test_the_page_can_switch_the_guard_on_and_off(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    with Shell(Static(tmp_path), window=None) as shell:
        token = shell.app.state.bootstrap_token

        def call(path: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
            connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
            connection.request(
                "POST",
                path,
                body=json.dumps(body),
                headers={
                    "Cookie": cookie,
                    "Origin": shell.base_url,
                    "Content-Type": "application/json",
                },
            )
            result: dict[str, Any] = json.loads(connection.getresponse().read())
            connection.close()
            return result

        sign_in = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
        sign_in.request("GET", f"/?cornea_token={token}")
        cookie = (sign_in.getresponse().getheader("Set-Cookie") or "").split(";")[0]
        sign_in.close()

        assert call("/api/window/close-guard", {"enabled": True}, cookie)["enabled"] is True
        assert shell.app.state.close_guard.holds() is True
        call("/api/window/close-guard", {"enabled": False}, cookie)
        assert shell.app.state.close_guard.holds() is False


def test_the_python_decorator_registers_a_guard(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    shell = Shell(Static(tmp_path), window=None)
    busy = {"yes": True}

    @shell.close_guard
    def running() -> bool:
        return busy["yes"]

    assert shell.app.state.close_guard.holds() is True
    busy["yes"] = False
    assert shell.app.state.close_guard.holds() is False


def test_the_close_route_reports_a_blocked_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    with Shell(Static(tmp_path), window=None) as shell:
        controller = SimpleNamespace(
            close=lambda force=False: bool(force), state=lambda: {}, headless=False
        )
        shell.app.state.window = controller
        sign_in = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
        sign_in.request("GET", f"/?cornea_token={shell.app.state.bootstrap_token}")
        cookie = (sign_in.getresponse().getheader("Set-Cookie") or "").split(";")[0]
        sign_in.close()

        def close(body: dict[str, Any] | None) -> dict[str, Any]:
            connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
            connection.request(
                "POST",
                "/api/window/close",
                body=json.dumps(body) if body is not None else None,
                headers={
                    "Cookie": cookie,
                    "Origin": shell.base_url,
                    "Content-Type": "application/json",
                },
            )
            result: dict[str, Any] = json.loads(connection.getresponse().read())
            connection.close()
            return result

        assert close(None) == {"ok": False, "blocked": True}
        assert close({"force": True}) == {"ok": True}


# ----- dropped files ----------------------------------------------------------------------------


class FakeDomEvents:
    def __init__(self) -> None:
        self.drop = FakeDrop()
        self.dragover = FakeDrop()


class FakeDrop:
    def __init__(self) -> None:
        self.handlers: list[Any] = []

    def __iadd__(self, handler: Any) -> "FakeDrop":
        self.handlers.append(handler)
        return self


def fake_dom(monkeypatch: pytest.MonkeyPatch, window: FakeWindow) -> FakeDomEvents:
    events = FakeDomEvents()
    window.dom = SimpleNamespace(document=SimpleNamespace(events=events))  # type: ignore[attr-defined]
    module = ModuleType("webview.dom")
    module.DOMEventHandler = lambda callback, prevent, stop: callback  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "webview.dom", module)
    return events


def test_dropped_files_reach_the_page_only_when_asked(
    webview: FakeWebview, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, _, _ = make(webview, Window(drop_files=True))
    events = fake_dom(monkeypatch, window)
    scripts: list[str] = []
    window.evaluate_js = lambda script: scripts.append(script)  # type: ignore[attr-defined]

    window.events.loaded.fire()
    window.events.loaded.fire()  # a second load does not add a second handler
    events.drop.handlers[0](
        {"dataTransfer": {"files": [{"pywebviewFullPath": "C:/a.txt"}, {"name": "no-path"}]}}
    )

    assert len(events.drop.handlers) == 1
    assert 'new CustomEvent("cornea:drop"' in scripts[0]
    assert '{"paths": ["C:/a.txt"]}' in scripts[0]


def test_nothing_is_listened_for_by_default(
    webview: FakeWebview, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, _, _ = make(webview)
    events = fake_dom(monkeypatch, window)

    window.events.loaded.fire()

    assert events.drop.handlers == []


# ----- opening files ----------------------------------------------------------------------------


@pytest.fixture
def launched(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    calls: list[Any] = []
    monkeypatch.setattr(bridge_module, "_windows", lambda: True)
    monkeypatch.setattr("cornea.core.bridge.os.startfile", calls.append, raising=False)
    monkeypatch.setattr("cornea.core.bridge.subprocess.Popen", lambda args: calls.append(args))
    return calls


async def call(name: str, arguments: dict[str, Any], registry: ActionRegistry) -> tuple[int, Any]:
    return await invoke_action(registry, name, arguments, None)


def run(function: Callable[..., Any], *args: Any) -> Any:
    import asyncio

    return asyncio.run(function(*args))


def test_open_file_and_reveal_are_off_by_default() -> None:
    assert "open_file" not in ActionRegistry().names()
    assert "reveal" not in ActionRegistry().names()
    assert {"open_file", "reveal"} <= set(ActionRegistry(open_files=True).names())


def test_a_bridge_setting_turns_them_on(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")

    shell = Shell(Static(tmp_path), window=None, bridge=Bridge(open_files=True))

    assert "open_file" in shell.actions.names()


def test_a_document_is_opened(launched: list[Any], tmp_path: Path) -> None:
    document = tmp_path / "notes.txt"
    document.write_text("hi", encoding="utf-8")

    status, body = run(call, "open_file", {"path": str(document)}, ActionRegistry(open_files=True))

    assert (status, body["result"]) == (200, {"opened": True})
    assert launched == [document.resolve()]


@pytest.mark.parametrize("name", ["tool.exe", "run.bat", "s.ps1", "link.lnk", "x.JS", "noext"])
def test_programs_and_scripts_are_refused(launched: list[Any], tmp_path: Path, name: str) -> None:
    target = tmp_path / name
    target.write_text("x", encoding="utf-8")

    status, body = run(call, "open_file", {"path": str(target)}, ActionRegistry(open_files=True))

    assert status == 422
    assert "cannot be opened" in body["error"]
    assert launched == []


def test_missing_paths_folders_and_network_paths_are_refused(
    launched: list[Any], tmp_path: Path
) -> None:
    registry = ActionRegistry(open_files=True)

    assert run(call, "open_file", {"path": str(tmp_path / "gone.txt")}, registry)[0] == 422
    assert "folder" in run(call, "open_file", {"path": str(tmp_path)}, registry)[1]["error"]
    assert (
        "network"
        in run(call, "open_file", {"path": "\\\\server\\share\\a.txt"}, registry)[1]["error"]
    )
    assert run(call, "open_file", {"path": ""}, registry)[0] == 422
    assert launched == []


def test_reveal_selects_a_file_and_opens_a_folder(launched: list[Any], tmp_path: Path) -> None:
    document = tmp_path / "a.txt"
    document.write_text("x", encoding="utf-8")
    registry = ActionRegistry(open_files=True)

    run(call, "reveal", {"path": str(document)}, registry)
    run(call, "reveal", {"path": str(tmp_path)}, registry)

    assert launched[0] == ["explorer", "/select,", str(document.resolve())]
    assert launched[1] == ["explorer", str(tmp_path.resolve())]


def test_reveal_can_show_a_program(launched: list[Any], tmp_path: Path) -> None:
    program = tmp_path / "tool.exe"
    program.write_text("x", encoding="utf-8")

    status, _ = run(call, "reveal", {"path": str(program)}, ActionRegistry(open_files=True))

    assert status == 200  # showing a file is not running it


def test_other_systems_say_it_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bridge_module, "_windows", lambda: False)
    document = tmp_path / "a.txt"
    document.write_text("x", encoding="utf-8")

    with pytest.raises(Unavailable):
        bridge_module.open_file(None, str(document))


def test_a_bad_path_is_bad_arguments() -> None:
    with pytest.raises(BadArguments):
        bridge_module.open_file(None, 5)  # type: ignore[arg-type]
