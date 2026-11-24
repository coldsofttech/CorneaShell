"""The taskbar button: what is allowed, the badge picture and how the pieces are wired."""

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from cornea import Bridge, JumpItem, Shell, Static, Window
from cornea.core.bridge import ActionRegistry
from cornea.core.bridge.bridge import LAUNCH
from cornea.core.page.taskbar import BADGE_SIZE, JUMP_ARGUMENT, Taskbar
from cornea.core.window.window import SimulatedWindow, Unavailable

# ----- what is allowed --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "value"),
    [("none", None), ("indeterminate", None), ("normal", 0), ("error", 50.5), ("paused", 100)],
)
def test_good_progress_passes(state: str, value: Any) -> None:
    assert Taskbar.check_progress(state, value)[0] == state


@pytest.mark.parametrize(
    ("state", "value", "problem"),
    [
        ("loud", None, "state must be"),
        (5, None, "state must be"),
        ("normal", None, "value is needed"),
        ("normal", -1, "0 to 100"),
        ("normal", 101, "0 to 100"),
        ("normal", "5", "0 to 100"),
        ("normal", True, "0 to 100"),
    ],
)
def test_bad_progress_is_refused(state: Any, value: Any, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        Taskbar.check_progress(state, value)


@pytest.mark.parametrize(
    ("count", "text"),
    [(None, None), (False, None), (0, None), (True, ""), (3, "3"), (99, "99"), (100, "99+")],
)
def test_the_badge_text(count: Any, text: str | None) -> None:
    assert Taskbar.check_badge(count) == text


@pytest.mark.parametrize("count", [-1, 1.5, "3", [1]])
def test_a_bad_badge_is_refused(count: Any) -> None:
    with pytest.raises(ValueError, match="count must be"):
        Taskbar.check_badge(count)


def test_items_can_be_objects_or_dicts() -> None:
    items = Taskbar.check_items([JumpItem("a", "A"), {"id": "b", "title": "B", "description": "d"}])

    assert [item.id for item in items] == ["a", "b"]


@pytest.mark.parametrize(
    ("items", "problem"),
    [
        ("abc", "must be a list"),
        ([JumpItem("a", "A")] * 11, "at most 10"),
        ([{"id": "a", "title": "A", "run": "calc"}], "unknown item fields"),
        (["x"], "each item must be"),
        ([{"id": "has space", "title": "A"}], "item id must be"),
        ([{"id": "a", "title": " "}], "item title must be"),
        ([{"id": "a", "title": "t" * 65}], "item title can have"),
        ([{"id": "a", "title": "new\nline"}], "item title can have"),
        ([{"id": "a", "title": "A", "description": "d" * 257}], "item description"),
        ([JumpItem("a", "A"), JumpItem("a", "B")], "unique"),
    ],
)
def test_bad_items_are_refused(items: Any, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        Taskbar.check_items(items)


# ----- the badge picture ------------------------------------------------------------------------


def _alpha(pixels: bytes, x: int, y: int) -> int:
    return pixels[(y * BADGE_SIZE + x) * 4 + 3]


def test_the_badge_is_a_disc_with_a_red_centre_and_clear_corners() -> None:
    pixels = Taskbar.badge_pixels("")

    assert len(pixels) == BADGE_SIZE * BADGE_SIZE * 4
    assert _alpha(pixels, 0, 0) == 0
    assert _alpha(pixels, BADGE_SIZE // 2, BADGE_SIZE // 2) == 255
    centre = (BADGE_SIZE // 2 * BADGE_SIZE + BADGE_SIZE // 2) * 4
    assert pixels[centre : centre + 3] == bytes((0x38, 0x34, 0xD1))  # blue, green, red


@pytest.mark.parametrize("text", ["7", "42", "99+"])
def test_the_count_is_drawn_in_white(text: str) -> None:
    pixels = Taskbar.badge_pixels(text)

    whites = [i for i in range(0, len(pixels), 4) if pixels[i : i + 3] == b"\xff\xff\xff"]
    assert whites
    assert pixels != Taskbar.badge_pixels("")


# ----- starting from a jump list entry ----------------------------------------------------------


def test_the_launch_argument_is_taken_out_of_argv() -> None:
    argv = ["app.py", "--debug", f"{JUMP_ARGUMENT}=new-note"]

    assert Taskbar.take_launch_item(argv) == "new-note"
    assert argv == ["app.py", "--debug"]


@pytest.mark.parametrize("bad", ["", "a b", "x" * 65, "a;b"])
def test_a_bad_launch_id_is_dropped_but_still_removed(bad: str) -> None:
    argv = ["app.py", f"{JUMP_ARGUMENT}={bad}"]

    assert Taskbar.take_launch_item(argv) is None
    assert argv == ["app.py"]


def test_a_normal_start_has_no_launch_item() -> None:
    assert Taskbar.take_launch_item(["app.py", "--debug"]) is None


def test_the_command_restarts_the_app_with_the_item(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "orig_argv", ["python", "my app.py", f"{JUMP_ARGUMENT}=old", "-v"])

    program, arguments = Taskbar.launch_command("new-note")

    assert program == sys.executable
    assert arguments == f'"my app.py" -v {JUMP_ARGUMENT}=new-note'


# ----- showing it -------------------------------------------------------------------------------


def test_other_systems_say_it_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    taskbar = Taskbar(None, lambda: 1)

    with pytest.raises(Unavailable, match="only works on Windows"):
        taskbar.set_progress("indeterminate")
    with pytest.raises(Unavailable, match="only works on Windows"):
        taskbar.set_badge(2)
    with pytest.raises(Unavailable, match="only works on Windows"):
        taskbar.set_jump_list([])


def test_bad_input_is_refused_before_windows_is_asked() -> None:
    taskbar = Taskbar(None, lambda: 1)

    with pytest.raises(ValueError, match="state must be"):
        taskbar.set_progress("loud")


# ----- the page and Python ----------------------------------------------------------------------


def test_the_actions_are_off_until_allowed() -> None:
    off = ActionRegistry().names()
    on = ActionRegistry(taskbar=True).names()

    for name in ("set_taskbar_progress", "set_taskbar_badge", "set_jump_list", "jump_list_launch"):
        assert name not in off
        assert name in on


def test_a_page_gets_a_clear_answer_without_a_window() -> None:
    actions = ActionRegistry(taskbar=True)

    status, body = asyncio.run(actions.invoke("set_taskbar_badge", {"count": 3}, None))

    assert status == 200
    assert body["available"] is False


def test_a_page_cannot_send_bad_input() -> None:
    actions = ActionRegistry(taskbar=True)

    status, _ = asyncio.run(actions.invoke("set_taskbar_progress", {"state": "x"}, None))

    assert status == 422


def test_the_page_can_ask_where_the_app_was_started_from() -> None:
    LAUNCH.item = "new-note"
    try:
        status, body = asyncio.run(
            ActionRegistry(taskbar=True).invoke("jump_list_launch", {}, None)
        )
    finally:
        LAUNCH.item = None

    assert status == 200
    assert body["result"] == {"id": "new-note"}


def test_the_controller_passes_the_work_to_the_taskbar(monkeypatch: pytest.MonkeyPatch) -> None:
    from cornea.core.window import window as window_module
    from window_fakes import FakeWebview

    monkeypatch.setattr(window_module, "_invoke", lambda native, function: function())
    webview = FakeWebview()
    _, controller = window_module.create_native_window(
        webview, "http://x", Window(), lambda error: None
    )
    seen: list[tuple[Any, ...]] = []

    class Spy(Taskbar):
        def set_progress(self, state: str, value: float | None = None) -> None:
            seen.append(("progress", state, value))

        def set_badge(self, count: object) -> None:
            seen.append(("badge", count))

        def set_jump_list(self, items: object) -> None:
            seen.append(("jump", len(self.check_items(items))))

    controller.taskbar = Spy(None, lambda: 1)
    controller.set_taskbar_progress("normal", 10)
    controller.set_taskbar_badge(4)
    controller.set_jump_list([{"id": "a", "title": "A"}])

    assert seen == [("progress", "normal", 10.0), ("badge", 4), ("jump", 1)]


def test_a_failure_on_the_ui_thread_reaches_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    from cornea.core.window import window as window_module
    from window_fakes import FakeWebview

    monkeypatch.setattr(window_module, "_invoke", lambda native, function: function())
    _, controller = window_module.create_native_window(
        FakeWebview(), "http://x", Window(), lambda error: None
    )

    class Broken(Taskbar):
        def set_badge(self, count: object) -> None:
            raise OSError("no")

    controller.taskbar = Broken(None, lambda: 1)

    with pytest.raises(OSError, match="no"):
        controller.set_taskbar_badge(1)


def test_a_controller_without_a_taskbar_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from cornea.core.window import window as window_module
    from window_fakes import FakeWebview

    _, controller = window_module.create_native_window(
        FakeWebview(), "http://x", Window(), lambda error: None
    )

    with pytest.raises(Unavailable, match="taskbar"):
        controller.set_jump_list([])


def test_the_simulated_window_has_no_taskbar() -> None:
    window = SimulatedWindow("Demo")

    calls: list[Callable[[], None]] = [
        lambda: window.set_taskbar_progress("none"),
        lambda: window.set_taskbar_badge(1),
        lambda: window.set_jump_list([]),
    ]
    for call in calls:
        with pytest.raises(Unavailable):
            call()


def test_shell_methods_check_then_need_a_window(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    shell = Shell(Static(tmp_path), window=None, bridge=Bridge(taskbar=True))

    with pytest.raises(ValueError, match="state must be"):
        shell.set_taskbar_progress("loud")
    with pytest.raises(ValueError, match="count must be"):
        shell.set_taskbar_badge(-2)
    with pytest.raises(ValueError, match="unique"):
        shell.set_jump_list([JumpItem("a", "A"), JumpItem("a", "B")])
    with pytest.raises(RuntimeError, match="no window"):
        shell.set_taskbar_progress("indeterminate")
    with pytest.raises(RuntimeError, match="no window"):
        shell.set_taskbar_badge(1)
    with pytest.raises(RuntimeError, match="no window"):
        shell.set_jump_list([])


def test_a_jump_from_a_second_copy_reaches_the_page(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    shell = Shell(Static(tmp_path), window=None)
    told: list[tuple[str, Any]] = []

    class Controller:
        def notify(self, event: str, detail: object = None) -> None:
            told.append((event, detail))

    shell.app.state.window = Controller()
    shell._on_jump("new-note")
    shell._on_jump("bad id")

    assert told == [("jump-list-click", {"id": "new-note"})]
