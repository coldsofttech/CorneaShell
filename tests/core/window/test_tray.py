"""The system tray: the menu, what closing does with a tray, and the shell's tray items."""

import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from cornea import Shell, Static, Window
from cornea.core.security.close_guard import CloseGuard
from cornea.core.window import tray as tray_module
from cornea.core.window import window as window_module
from cornea.core.window.tray import (
    FIRST_ITEM_ID,
    MAX_LABEL,
    MAX_TOOLTIP,
    QUIT_ID,
    SHOW_ID,
    Tray,
    TrayItems,
)
from cornea.core.window.window import NativeWindow
from window_fakes import FakeWebview, FakeWindow


class FakeBackend:
    """Records what the tray asks of Windows, and answers the menu with a chosen entry."""

    def __init__(self) -> None:
        self.started: tuple[str, Path | None] | None = None
        self.tooltips: list[str] = []
        self.menus: list[list[tuple[int, str]]] = []
        self.choice: int | None = None
        self.stops = 0
        self.on_event: Callable[[str], None] = lambda event: None

    def start(self, tooltip: str, icon: Path | None, on_event: Callable[[str], None]) -> None:
        self.started = (tooltip, icon)
        self.on_event = on_event

    def set_tooltip(self, tooltip: str) -> None:
        self.tooltips.append(tooltip)

    def choose(self, entries: list[tuple[int, str]]) -> int | None:
        self.menus.append(entries)
        return self.choice

    def stop(self) -> None:
        self.stops += 1


def wait_for(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 2
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert condition()


def make_tray(
    items: TrayItems | None = None, title: str = "App"
) -> tuple[Tray, FakeBackend, list[str]]:
    backend = FakeBackend()
    calls: list[str] = []
    tray = Tray(
        title,
        Path("icon.ico"),
        items or TrayItems(),
        show=lambda: calls.append("show"),
        quit=lambda: calls.append("quit"),
        backend=backend,
    )
    return tray, backend, calls


# ----- the items --------------------------------------------------------------------------------


def test_items_keep_their_order() -> None:
    items = TrayItems()
    items.add("Sync now", lambda: None)
    items.add("Pause", lambda: None)

    assert items.labels() == ["Sync now", "Pause"]
    assert len(items) == 2


@pytest.mark.parametrize(
    ("label", "message"),
    [
        ("", "needs a label"),
        ("   ", "needs a label"),
        ("x" * (MAX_LABEL + 1), "at most 64"),
        ("Show", "already has"),
        ("quit", "already has"),
    ],
)
def test_bad_labels_are_refused(label: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        TrayItems().add(label, lambda: None)


def test_a_label_cannot_be_used_twice() -> None:
    items = TrayItems()
    items.add("Sync now", lambda: None)

    with pytest.raises(ValueError, match="already has"):
        items.add("Sync now", lambda: None)


# ----- the tray ---------------------------------------------------------------------------------


def test_the_icon_gets_the_title_as_its_tooltip() -> None:
    tray, backend, _ = make_tray(title="Notes")

    tray.start()
    tray.start()

    assert backend.started == ("Notes", Path("icon.ico"))


def test_a_long_title_is_cut_to_fit_the_tooltip() -> None:
    tooltip = Tray.tooltip_for("T" * 500)

    assert len(tooltip) == MAX_TOOLTIP
    assert tooltip.endswith("…")


def test_a_new_title_updates_the_tooltip_once_shown() -> None:
    tray, backend, _ = make_tray()
    tray.set_title("Before start")
    tray.start()

    tray.set_title("Renamed")

    assert backend.tooltips == ["Renamed"]


def test_the_menu_is_show_the_apps_items_then_quit() -> None:
    items = TrayItems()
    items.add("Sync now", lambda: None)
    tray, _, _ = make_tray(items)

    assert tray.entries() == [
        (SHOW_ID, "Show"),
        (FIRST_ITEM_ID, "Sync now"),
        (0, ""),
        (QUIT_ID, "Quit"),
    ]


def test_clicking_the_icon_shows_the_window() -> None:
    tray, backend, calls = make_tray()
    tray.start()

    backend.on_event("click")

    wait_for(lambda: calls == ["show"])


@pytest.mark.parametrize(("choice", "expected"), [(SHOW_ID, "show"), (QUIT_ID, "quit")])
def test_the_menu_runs_show_and_quit(choice: int, expected: str) -> None:
    tray, backend, calls = make_tray()
    tray.start()
    backend.choice = choice

    backend.on_event("menu")

    wait_for(lambda: calls == [expected])
    assert len(backend.menus) == 1


def test_the_menu_runs_the_apps_items() -> None:
    ran = threading.Event()
    items = TrayItems()
    items.add("Other", lambda: None)
    items.add("Sync now", ran.set)
    tray, backend, _ = make_tray(items)
    tray.start()
    backend.choice = FIRST_ITEM_ID + 1

    backend.on_event("menu")

    assert ran.wait(2)


def test_dismissing_the_menu_does_nothing() -> None:
    tray, backend, calls = make_tray()
    tray.start()

    backend.on_event("menu")
    backend.on_event("restart")
    time.sleep(0.05)

    assert calls == []


def test_a_failing_item_is_logged_and_the_tray_carries_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    items = TrayItems()

    def broken() -> None:
        raise RuntimeError("boom")

    items.add("Broken", broken)
    tray, backend, calls = make_tray(items)
    tray.start()
    backend.choice = FIRST_ITEM_ID

    with caplog.at_level("ERROR"):
        backend.on_event("menu")
        wait_for(lambda: "The tray item 'Broken' failed" in caplog.text)
    backend.choice = SHOW_ID
    backend.on_event("menu")

    wait_for(lambda: calls == ["show"])


def test_stopping_removes_the_icon_once() -> None:
    tray, backend, _ = make_tray()
    tray.stop()
    tray.start()

    tray.stop()
    tray.stop()

    assert backend.stops == 1


@pytest.mark.skipif(sys.platform == "win32", reason="checks the failure off Windows")
def test_the_real_backend_needs_windows() -> None:
    tray = Tray("App", None, TrayItems(), show=lambda: None, quit=lambda: None)

    with pytest.raises(RuntimeError, match="could not be created"):
        tray.start()


# ----- the window with a tray -------------------------------------------------------------------


def make_window(
    guard: CloseGuard | None = None,
) -> tuple[NativeWindow, FakeWindow, Tray, list[str]]:
    fake = FakeWindow("App", "http://x")
    controller = NativeWindow(fake, Window(tray=True))
    scripts: list[str] = []
    fake.evaluate_js = lambda script: scripts.append(script)  # type: ignore[attr-defined]
    tray, backend, _ = make_tray()
    tray.start()
    controller.tray = tray
    controller.guard = guard
    controller.backend = backend  # type: ignore[attr-defined]
    return controller, fake, tray, scripts


def test_closing_the_window_hides_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window_module, "CLOSE_DELAY", 0)
    controller, fake, _, _ = make_window()

    allowed = all(handler() is not False for handler in fake.events.closing.handlers)
    time.sleep(0.05)

    assert not allowed
    assert fake.calls == ["hide"]
    assert controller.state()["hidden"] is True


def test_closing_from_the_page_hides_it_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window_module, "CLOSE_DELAY", 0)
    controller, fake, _, _ = make_window()

    assert controller.close() is True
    time.sleep(0.05)

    assert fake.calls == ["hide"]


def test_hiding_does_not_ask_the_close_guard() -> None:
    guard = CloseGuard()
    guard.add(lambda: True)
    controller, fake, _, scripts = make_window(guard)

    controller.close()

    assert fake.calls == ["hide"]
    assert scripts == []


def test_forcing_the_close_stops_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window_module, "CLOSE_DELAY", 0)
    controller, fake, _, _ = make_window()

    assert controller.close(force=True) is True
    time.sleep(0.05)
    allowed = all(handler() is not False for handler in fake.events.closing.handlers)

    assert fake.calls == ["destroy"]
    assert allowed


def test_showing_the_window_brings_it_back() -> None:
    controller, fake, _, _ = make_window()
    controller.hide()

    controller.activate()

    assert controller.state()["hidden"] is False
    assert fake.calls[-1] == "show"


def test_quit_stops_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window_module, "CLOSE_DELAY", 0)
    controller, fake, _, _ = make_window()

    assert controller.quit() is True
    time.sleep(0.05)

    assert fake.calls == ["destroy"]


def test_quit_shows_the_window_and_asks_when_the_app_holds_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(window_module, "_invoke", lambda native, function: function())
    monkeypatch.setattr(window_module, "bring_to_front", lambda window: None)
    guard = CloseGuard()
    guard.add(lambda: True)
    controller, fake, _, scripts = make_window(guard)
    controller.hide()

    assert controller.quit() is False

    assert fake.calls == ["hide", "show"]
    assert "cornea:close-blocked" in scripts[0]
    assert controller.state()["hidden"] is False


def test_a_new_title_reaches_the_tooltip() -> None:
    controller, _, tray, _ = make_window()
    backend = controller.backend  # type: ignore[attr-defined]

    controller.set_title("Renamed")

    assert backend.tooltips == ["Renamed"]
    assert tray is controller.tray


def test_without_a_tray_closing_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window_module, "CLOSE_DELAY", 0)
    fake = FakeWindow("App", "http://x")
    controller = NativeWindow(fake, Window())

    controller.close()
    time.sleep(0.05)

    assert fake.calls == ["destroy"]


# ----- the shell --------------------------------------------------------------------------------


@pytest.fixture
def webview(monkeypatch: pytest.MonkeyPatch) -> FakeWebview:
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(window_module, "_registry_version", lambda: "130.0.1")
    monkeypatch.setattr(window_module, "_invoke", lambda native, function: function())
    monkeypatch.setattr(window_module, "CLOSE_DELAY", 0)
    monkeypatch.setattr(window_module, "require_windows", lambda: None)
    return fake


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> FakeBackend:
    fake = FakeBackend()
    monkeypatch.setattr(tray_module, "Win32Backend", lambda: fake)
    return fake


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    return tmp_path


def test_tray_items_need_a_tray() -> None:
    with pytest.raises(ValueError, match="tray=True"):
        Shell(window=None).tray_item("Sync now")
    with pytest.raises(ValueError, match="tray=True"):
        Shell(window=Window()).tray_item("Sync now")


def test_tray_items_are_collected_in_order() -> None:
    shell = Shell(window=Window(tray=True))

    @shell.tray_item("Sync now")
    def sync() -> None: ...

    shell.tray_item("Pause")(lambda: None)

    assert shell.tray_labels == ["Sync now", "Pause"]
    assert callable(sync)


def test_a_bad_tray_item_is_refused() -> None:
    shell = Shell(window=Window(tray=True))

    with pytest.raises(ValueError, match="at most"):
        shell.tray_item("x" * 100)(lambda: None)


def test_the_tray_is_shown_for_the_run_and_removed_after(
    webview: FakeWebview, backend: FakeBackend, bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cornea.core.shell.require_webview2", lambda: "130.0.1")
    monkeypatch.setattr("cornea.core.shell.require_windows", lambda: None)
    shell = Shell(Static(bundle), window=Window(title="Notes", tray=True), loading=None)
    shell.tray_item("Sync now")(lambda: None)
    seen: dict[str, object] = {}

    def while_open(window: FakeWindow) -> None:
        seen["stops"] = backend.stops
        seen["entries"] = [label for _, label in shell.app.state.window.tray.entries()]

    webview.while_open = while_open
    shell.run()

    assert backend.started == ("Notes", None)
    assert seen["stops"] == 0
    assert seen["entries"] == ["Show", "Sync now", "", "Quit"]
    assert backend.stops == 1


def test_no_tray_is_made_unless_asked(
    webview: FakeWebview, backend: FakeBackend, bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cornea.core.shell.require_webview2", lambda: "130.0.1")
    monkeypatch.setattr("cornea.core.shell.require_windows", lambda: None)

    Shell(Static(bundle), window=Window(), loading=None).run()

    assert backend.started is None
