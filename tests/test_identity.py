"""The App identity: window memory, the single-instance lock and the taskbar identity."""

import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cornea import App, Shell, Static, Window
from cornea.core import shell as shell_module
from cornea.core import window as window_module
from cornea.core.appdata import data_dir
from cornea.core.single_instance import (
    INFO_FILE,
    AlreadyRunning,
    InstanceLock,
    activate_existing,
)
from cornea.core.window import NativeWindow, create_native_window
from cornea.core.window_memory import MIN_VISIBLE, Remembered, WindowMemory, fit_to_screens
from test_window import FakeEvent, FakeWebview, FakeWindow

SCREEN = (0, 0, 1920, 1080)


@pytest.fixture(autouse=True)
def local_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every app's files in the test's own folder."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    return tmp_path / "local"


def unique_id() -> str:
    """Mutex names are global to the machine, so every test gets its own app id."""
    return f"test-{uuid.uuid4().hex[:10]}"


# ----- the App settings -----------------------------------------------------------------------


def test_app_defaults_are_all_off() -> None:
    app = App()

    assert (app.id, app.single_instance, app.remember_window) == (None, False, False)


@pytest.mark.parametrize("app_id", ["notes", "com.example.notes", "my-app_2", "A" * 128])
def test_good_app_ids(app_id: str) -> None:
    assert App(id=app_id).id == app_id


@pytest.mark.parametrize(
    "app_id", ["", " ", "-start", ".start", "has space", "a/b", "a\\b", "A" * 129]
)
def test_bad_app_ids(app_id: str) -> None:
    with pytest.raises(ValueError, match="id may use"):
        App(id=app_id)


@pytest.mark.parametrize("option", ["single_instance", "remember_window"])
def test_those_options_need_an_id(option: str) -> None:
    with pytest.raises(ValueError, match="need an id"):
        App(**{option: True})  # type: ignore[arg-type]


def test_an_id_alone_only_names_the_app() -> None:
    assert App(id="notes").single_instance is False


def test_data_lives_under_the_local_app_data_folder(local_data: Path) -> None:
    folder = data_dir("notes")

    assert folder == local_data / "Cornea" / "notes"
    assert folder.is_dir()


def test_single_instance_and_memory_need_a_window() -> None:
    for identity in (
        App(id="a", single_instance=True),
        App(id="a", remember_window=True),
    ):
        with pytest.raises(ValueError, match="need a window"):
            Shell(Static("."), window=None, identity=identity)


# ----- remembering a window -------------------------------------------------------------------


def test_a_window_is_saved_and_loaded(tmp_path: Path) -> None:
    memory = WindowMemory(tmp_path / "window.json")
    place = Remembered(900, 600, 40, 50, True)

    memory.save(place)

    assert memory.load() == place
    assert not list(tmp_path.glob("*.tmp"))


def test_a_window_that_was_never_placed_is_loaded(tmp_path: Path) -> None:
    memory = WindowMemory(tmp_path / "window.json")
    memory.save(Remembered(900, 600))

    assert memory.load() == Remembered(900, 600, None, None, False)


def test_nothing_remembered_means_none(tmp_path: Path) -> None:
    assert WindowMemory(tmp_path / "missing.json").load() is None


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        "{}",
        '{"width": 100}',
        '{"width": -1, "height": 100}',
        '{"width": 100, "height": 0}',
        '{"width": "wide", "height": 100}',
        '{"width": 100, "height": 100, "x": 5}',
    ],
)
def test_a_damaged_file_is_ignored(content: str, tmp_path: Path) -> None:
    path = tmp_path / "window.json"
    path.write_text(content, encoding="utf-8")

    assert WindowMemory(path).load() is None


def test_the_size_is_never_below_the_minimum() -> None:
    fitted = fit_to_screens(Remembered(50, 40, 10, 10), [SCREEN], (400, 300))

    assert (fitted.width, fitted.height) == (400, 300)


def test_a_position_on_a_screen_is_kept() -> None:
    fitted = fit_to_screens(Remembered(800, 600, 100, 80), [SCREEN], (200, 100))

    assert (fitted.x, fitted.y) == (100, 80)


def test_a_position_on_a_second_monitor_to_the_left_is_kept() -> None:
    screens = [SCREEN, (-1920, 0, 1920, 1080)]

    assert fit_to_screens(Remembered(800, 600, -1500, 100), screens, (200, 100)).x == -1500


@pytest.mark.parametrize(
    ("x", "y"),
    [(5000, 100), (100, 5000), (-5000, 100), (-32000, -32000), (1900, 100), (100, 1070)],
)
def test_a_position_that_is_off_every_screen_is_dropped(x: int, y: int) -> None:
    fitted = fit_to_screens(Remembered(800, 600, x, y), [SCREEN], (200, 100))

    assert (fitted.x, fitted.y) == (None, None)
    assert (fitted.width, fitted.height) == (800, 600)


def test_the_corner_must_have_room_to_grab() -> None:
    need_width, _ = MIN_VISIBLE
    edge = SCREEN[2] - need_width

    assert fit_to_screens(Remembered(800, 600, edge, 0), [SCREEN], (200, 100)).x == edge
    assert fit_to_screens(Remembered(800, 600, edge + 1, 0), [SCREEN], (200, 100)).x is None


def test_without_screen_information_the_position_is_kept() -> None:
    assert fit_to_screens(Remembered(800, 600, 9999, 9999), [], (200, 100)).x == 9999


def test_the_maximized_state_is_kept() -> None:
    assert fit_to_screens(Remembered(800, 600, 1, 1, True), [SCREEN], (200, 100)).maximized


# ----- following the window -------------------------------------------------------------------


def native(position: tuple[int, int] | None = None) -> tuple[NativeWindow, FakeWindow]:
    fake = FakeWindow("t", "u")
    return NativeWindow(fake, Window(size=(900, 600), position=position)), fake


def test_the_window_starts_where_the_settings_put_it() -> None:
    controller, _ = native(position=(30, 40))

    assert controller.remember() == Remembered(900, 600, 30, 40, False)


def test_moves_and_resizes_are_followed() -> None:
    controller, fake = native(position=(30, 40))

    fake.events.moved.fire(100, 120)
    fake.events.resized.fire(1000, 700)

    assert controller.remember() == Remembered(1000, 700, 100, 120, False)


def test_a_maximized_window_remembers_its_normal_place() -> None:
    controller, fake = native(position=(30, 40))
    fake.events.moved.fire(100, 120)
    fake.events.resized.fire(1000, 700)

    fake.events.maximized.fire()
    fake.events.resized.fire(1920, 1040)
    fake.events.moved.fire(0, 0)

    assert controller.remember() == Remembered(1000, 700, 100, 120, True)


def test_following_resumes_after_a_restore() -> None:
    controller, fake = native(position=(30, 40))
    fake.events.maximized.fire()
    fake.events.restored.fire()

    fake.events.resized.fire(800, 500)

    assert controller.remember().width == 800
    assert controller.remember().maximized is False


def test_a_minimized_window_is_not_remembered_off_screen() -> None:
    controller, fake = native(position=(30, 40))

    fake.events.minimized.fire()
    fake.events.moved.fire(-32000, -32000)

    assert (controller.remember().x, controller.remember().y) == (30, 40)


def test_nonsense_positions_and_sizes_are_ignored() -> None:
    controller, fake = native(position=(30, 40))

    fake.events.moved.fire(-32000, 10)
    fake.events.resized.fire(0, 0)

    assert controller.remember() == Remembered(900, 600, 30, 40, False)


def test_a_window_placed_by_the_system_is_asked_where_it_is() -> None:
    controller, fake = native()
    fake.x, fake.y = 210, 160  # type: ignore[attr-defined]

    assert controller.remember() == Remembered(900, 600, 210, 160, False)


def test_a_window_that_cannot_say_where_it_is_stays_unplaced() -> None:
    controller, _ = native()

    assert controller.remember() == Remembered(900, 600, None, None, False)


def test_a_remembered_start_is_the_first_place() -> None:
    fake = FakeWindow("t", "u")
    controller = NativeWindow(fake, Window(), None, Remembered(700, 500, 20, 30, True))

    assert controller.remember() == Remembered(700, 500, 20, 30, True)
    assert controller.state()["maximized"] is True


# ----- creating the window with a memory ------------------------------------------------------


class Screen:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x, self.y, self.width, self.height = x, y, width, height


@pytest.fixture
def webview(monkeypatch: pytest.MonkeyPatch) -> FakeWebview:
    fake = FakeWebview()
    fake.screens = lambda: [Screen(*SCREEN)]  # type: ignore[attr-defined]
    ids: list[str] = []
    monkeypatch.setattr(window_module, "set_app_user_model_id", ids.append)
    fake.taskbar_ids = ids  # type: ignore[attr-defined]
    return fake


def create(
    webview: FakeWebview, app: App | None, settings: Window | None = None
) -> tuple[FakeWindow, NativeWindow]:
    window, controller = create_native_window(
        webview, "http://x", settings or Window(), lambda error: None, app
    )
    return window, controller


def write_memory(app_id: str, place: dict[str, Any]) -> Path:
    path = data_dir(app_id) / "window.json"
    path.write_text(json.dumps(place), encoding="utf-8")
    return path


def test_the_window_reopens_where_it_was(webview: FakeWebview) -> None:
    app = App(id="notes", remember_window=True)
    write_memory("notes", {"width": 1100, "height": 750, "x": 200, "y": 120, "maximized": True})

    window, _ = create(webview, app)

    options = window.options
    assert (options["width"], options["height"]) == (1100, 750)
    assert (options["x"], options["y"], options["maximized"]) == (200, 120, True)


def test_nothing_is_remembered_unless_asked(webview: FakeWebview) -> None:
    write_memory("notes", {"width": 1100, "height": 750, "x": 200, "y": 120})

    window, _ = create(webview, App(id="notes"), Window(size=(640, 480)))

    assert (window.options["width"], window.options["height"]) == (640, 480)
    assert window.options["x"] is None


def test_without_a_saved_place_the_settings_are_used(webview: FakeWebview) -> None:
    window, _ = create(webview, App(id="notes", remember_window=True), Window(size=(640, 480)))

    assert (window.options["width"], window.options["height"]) == (640, 480)
    assert window.options["maximized"] is False


def test_an_unplugged_monitor_does_not_hide_the_window(webview: FakeWebview) -> None:
    write_memory("notes", {"width": 800, "height": 600, "x": 4000, "y": 100})

    window, _ = create(webview, App(id="notes", remember_window=True))

    assert (window.options["x"], window.options["y"]) == (None, None)
    assert window.options["width"] == 800


def test_a_saved_size_below_the_minimum_is_raised(webview: FakeWebview) -> None:
    write_memory("notes", {"width": 50, "height": 40})

    window, _ = create(webview, App(id="notes", remember_window=True), Window(min_size=(300, 200)))

    assert (window.options["width"], window.options["height"]) == (300, 200)


def test_closing_saves_the_place(webview: FakeWebview) -> None:
    window, _ = create(webview, App(id="notes", remember_window=True), Window(size=(900, 600)))
    window.events.moved.fire(60, 70)
    window.events.resized.fire(1000, 650)

    window.events.closing.fire()

    saved = json.loads((data_dir("notes") / "window.json").read_text(encoding="utf-8"))
    assert saved == {"width": 1000, "height": 650, "x": 60, "y": 70, "maximized": False}


def test_closing_a_maximized_window_saves_the_normal_place(webview: FakeWebview) -> None:
    window, _ = create(webview, App(id="notes", remember_window=True))
    window.events.moved.fire(60, 70)
    window.events.resized.fire(1000, 650)
    window.events.maximized.fire()
    window.events.resized.fire(1920, 1040)

    window.events.closing.fire()

    saved = json.loads((data_dir("notes") / "window.json").read_text(encoding="utf-8"))
    assert saved == {"width": 1000, "height": 650, "x": 60, "y": 70, "maximized": True}


def test_a_window_is_not_saved_unless_asked(webview: FakeWebview) -> None:
    window, _ = create(webview, App(id="notes"))

    window.events.closing.fire()

    assert not (data_dir("notes") / "window.json").exists()
    # Only the close guard listens, and it lets the window close.
    assert len(window.events.closing.handlers) == 1


def test_a_save_that_fails_never_stops_the_window_closing(
    webview: FakeWebview, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(self: WindowMemory, remembered: Remembered) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(WindowMemory, "save", fail)
    window, _ = create(webview, App(id="notes", remember_window=True))

    window.events.closing.fire()  # must not raise


def test_the_taskbar_identity_is_set_from_the_id(webview: FakeWebview) -> None:
    create(webview, App(id="com.example.notes"))
    create(webview, App())
    create(webview, None)

    assert webview.taskbar_ids == ["com.example.notes"]


def test_restoring_a_minimized_window_shows_and_raises_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raised: list[object] = []
    monkeypatch.setattr(window_module, "bring_to_front", raised.append)
    controller, fake = native()
    fake.events.minimized.fire()

    controller.activate()

    assert fake.calls == ["restore", "show"]
    assert raised == [fake]


def test_activating_a_normal_window_does_not_change_its_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(window_module, "bring_to_front", lambda window: None)
    controller, fake = native()
    fake.events.maximized.fire()

    controller.activate()

    assert fake.calls == ["show"]


def test_a_failure_to_raise_the_window_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(window: object) -> None:
        raise RuntimeError("no UI thread")

    monkeypatch.setattr(window_module, "bring_to_front", fail)
    controller, _ = native()

    controller.activate()  # must not raise


# ----- the single-instance lock ---------------------------------------------------------------


def test_only_one_copy_can_take_the_lock() -> None:
    app_id = unique_id()
    first, second = InstanceLock(app_id), InstanceLock(app_id)

    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_different_apps_do_not_share_a_lock() -> None:
    first, second = InstanceLock(unique_id()), InstanceLock(unique_id())

    assert first.acquire()
    assert second.acquire()
    first.release()
    second.release()


def test_releasing_is_safe_to_repeat() -> None:
    lock = InstanceLock(unique_id())
    lock.acquire()

    lock.release()
    lock.release()
    InstanceLock(unique_id()).release()


def test_a_second_copy_can_wake_the_first() -> None:
    app_id = unique_id()
    first = InstanceLock(app_id)
    first.acquire()
    woken: list[int] = []
    first.serve(lambda: woken.append(1))
    try:
        assert activate_existing(app_id) is True
        assert activate_existing(app_id) is True
    finally:
        first.release()

    assert woken == [1, 1]


def test_waking_needs_the_secret() -> None:
    app_id = unique_id()
    first = InstanceLock(app_id)
    first.acquire()
    woken: list[int] = []
    first.serve(lambda: woken.append(1))
    try:
        info = json.loads((data_dir(app_id) / INFO_FILE).read_text(encoding="utf-8"))
        info["secret"] = "guessed"  # noqa: S105
        (data_dir(app_id) / INFO_FILE).write_text(json.dumps(info), encoding="utf-8")

        assert activate_existing(app_id) is False
    finally:
        first.release()

    assert woken == []


def test_a_failing_wake_up_does_not_stop_the_first_copy() -> None:
    app_id = unique_id()
    first = InstanceLock(app_id)
    first.acquire()
    calls: list[int] = []

    def wake() -> None:
        calls.append(1)
        raise RuntimeError("cannot focus")

    first.serve(wake)
    try:
        activate_existing(app_id)
        activate_existing(app_id)
    finally:
        first.release()

    assert calls == [1, 1]


def test_nobody_to_wake_means_false() -> None:
    assert activate_existing(unique_id()) is False


def test_a_leftover_file_from_a_crashed_copy_is_not_trusted() -> None:
    app_id = unique_id()
    info = {"port": 9, "secret": "x"}  # nothing listens on port 9
    (data_dir(app_id) / INFO_FILE).write_text(json.dumps(info), encoding="utf-8")

    assert activate_existing(app_id) is False


@pytest.mark.parametrize("content", ["not json", "{}", '{"port": "x", "secret": "y"}'])
def test_a_damaged_info_file_means_false(content: str) -> None:
    app_id = unique_id()
    (data_dir(app_id) / INFO_FILE).write_text(content, encoding="utf-8")

    assert activate_existing(app_id) is False


def test_releasing_removes_the_info_file() -> None:
    app_id = unique_id()
    lock = InstanceLock(app_id)
    lock.acquire()
    lock.serve(lambda: None)
    assert (data_dir(app_id) / INFO_FILE).exists()

    lock.release()

    assert not (data_dir(app_id) / INFO_FILE).exists()


def test_the_message_says_what_happened() -> None:
    assert "brought its window to the front" in str(AlreadyRunning("notes", activated=True))
    assert "could not reach its window" in str(AlreadyRunning("notes", activated=False))
    assert AlreadyRunning("notes", activated=True).activated is True


# ----- the shell ------------------------------------------------------------------------------


@pytest.fixture
def window_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    """Pretend a window can be shown, and record what the shell asks for."""
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)  # so Static(".") is a real bundle
    events: list[str] = []
    monkeypatch.setattr(window_module, "_registry_version", lambda: "1")
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace())

    def create_window(
        webview: Any,
        url: str,
        settings: Any,
        on_error: Any,
        app: Any = None,
        on_event: Any = None,
        actions: Any = None,
    ) -> Any:
        events.append(f"window:{app.id if app else None}")
        return None, SimpleNamespace(activate=lambda: events.append("activated"))

    monkeypatch.setattr(shell_module, "create_native_window", create_window)
    monkeypatch.setattr(shell_module, "show_window", lambda *args: events.append("shown"))
    return events


def test_a_second_copy_wakes_the_first_and_does_not_start(window_environment: list[str]) -> None:
    app_id = unique_id()
    first = InstanceLock(app_id)
    first.acquire()
    first.serve(lambda: window_environment.append("first woken"))
    second = Shell(Static("."), identity=App(id=app_id, single_instance=True))
    try:
        with pytest.raises(AlreadyRunning) as caught:
            second.run()
    finally:
        first.release()

    assert caught.value.activated is True
    assert window_environment == ["first woken"]
    assert not second.running


def test_an_unreachable_first_copy_is_reported(window_environment: list[str]) -> None:
    app_id = unique_id()
    first = InstanceLock(app_id)
    first.acquire()  # holds the lock but never serves: like a copy that is still starting
    try:
        with pytest.raises(AlreadyRunning) as caught:
            Shell(Static("."), identity=App(id=app_id, single_instance=True)).run()
    finally:
        first.release()

    assert caught.value.activated is False


def test_the_first_copy_takes_the_lock_serves_and_lets_go(window_environment: list[str]) -> None:
    app_id = unique_id()
    shell = Shell(Static("."), identity=App(id=app_id, single_instance=True))

    shell.run(on_ready=lambda ready: window_environment.append("ready"))

    assert window_environment == ["ready", f"window:{app_id}", "shown"]
    again = InstanceLock(app_id)
    assert again.acquire()  # the lock was released when the window closed
    again.release()


def test_the_lock_is_only_taken_when_asked(window_environment: list[str]) -> None:
    app_id = unique_id()
    held = InstanceLock(app_id)
    held.acquire()
    try:
        Shell(Static("."), identity=App(id=app_id)).run()  # not single-instance: runs anyway
    finally:
        held.release()

    assert "shown" in window_environment


def test_two_copies_without_the_lock_run_independently(window_environment: list[str]) -> None:
    Shell(Static("."), identity=App(id="notes")).run()
    Shell(Static("."), identity=App(id="notes")).run()

    assert window_environment.count("shown") == 2


def test_event_fake_still_accepts_arguments() -> None:
    event = FakeEvent()
    seen: list[tuple[int, int]] = []
    event += lambda x, y: seen.append((x, y))

    event.fire(1, 2)

    assert seen == [(1, 2)]
