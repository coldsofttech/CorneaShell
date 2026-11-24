from typing import Any

import pytest

from cornea import Window
from cornea.core.window import window as window_module
from cornea.core.window.window import (
    NativeWindow,
    SimulatedWindow,
    check_coordinate,
    check_limit,
    check_side,
)
from window_fakes import FakeWindow


@pytest.fixture(autouse=True)
def no_ui_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window_module, "_invoke", lambda native, function: function())


def native() -> tuple[NativeWindow, FakeWindow]:
    fake = FakeWindow("t", "u")
    return NativeWindow(fake, Window(on_top=True)), fake


def test_always_on_top_starts_from_the_settings_and_can_change() -> None:
    controller, fake = native()
    assert controller.state()["always_on_top"] is True
    controller.set_always_on_top(False)
    assert fake.on_top is False
    assert controller.state()["always_on_top"] is False


def test_fullscreen_only_toggles_when_it_changes() -> None:
    controller, fake = native()
    controller.set_fullscreen(True)
    controller.set_fullscreen(True)
    assert fake.calls == ["toggle_fullscreen"]
    controller.set_fullscreen(False)
    assert fake.calls == ["toggle_fullscreen"] * 2
    assert controller.state()["fullscreen"] is False


def test_size_limits_are_stored_and_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    controller, _ = native()
    applied: list[Any] = []
    monkeypatch.setattr(window_module, "apply_size_limits", lambda *args: applied.append(args))
    controller.set_size_limits((500, 400), (900, 700))
    assert len(applied) == 1
    assert controller.state()["min_size"] == (500, 400)
    assert controller.state()["max_size"] == (900, 700)
    with pytest.raises(ValueError, match="smallest"):
        controller.set_size_limits((900, 700), (500, 400))


def test_bounds_follow_the_window_and_can_be_set() -> None:
    controller, fake = native()
    fake.events.moved.fire(30, 40)
    fake.events.resized.fire(700, 500)
    assert controller.bounds() == {"x": 30, "y": 40, "width": 700, "height": 500}
    controller.set_bounds(x=5, y=6)
    controller.set_bounds(width=800, height=600)
    assert fake.calls == ["move:5,6", "resize:800x600"]
    assert controller.bounds() == {"x": 5, "y": 6, "width": 800, "height": 600}


@pytest.mark.parametrize(
    "arguments",
    [{}, {"x": 1}, {"width": 300}, {"x": 99999, "y": 0}, {"width": 5, "height": 400}],
)
def test_bad_bounds_are_refused_before_the_window_moves(arguments: dict[str, Any]) -> None:
    controller, fake = native()
    with pytest.raises(ValueError, match=r"together|position|whole number"):
        controller.set_bounds(**arguments)
    assert fake.calls == []


def test_the_simulated_window_has_the_same_controls() -> None:
    window = SimulatedWindow("Demo")
    window.set_always_on_top(True)
    window.set_fullscreen(True)
    window.set_size_limits((300, 300), None)
    window.set_bounds(x=1, y=2, width=640, height=480)
    state = window.state()
    assert (state["always_on_top"], state["fullscreen"], state["min_size"]) == (
        True,
        True,
        (300, 300),
    )
    assert window.bounds() == {"x": 1, "y": 2, "width": 640, "height": 480}


def test_value_checks() -> None:
    assert check_limit(None, "m") is None
    assert check_limit([100, 200], "m") == (100, 200)
    assert check_coordinate(-1500, "x") == -1500
    for bad in (True, 1.5, "3", 10**6):
        with pytest.raises(ValueError, match="whole number"):
            check_side(bad, "width")
    with pytest.raises(ValueError, match="width and a height"):
        check_limit([1], "m")
