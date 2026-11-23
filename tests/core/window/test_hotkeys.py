"""Global hotkeys: parsing, the rules around them, and the show/hide toggle."""

import sys
from collections.abc import Callable

import pytest

from cornea import Shell, Window
from cornea.core.window import window as window_module
from cornea.core.window.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_WIN,
    Hotkey,
    Hotkeys,
    Win32Hotkeys,
    parse_hotkey,
)
from cornea.core.window.window import SimulatedWindow, create_native_window
from window_fakes import FakeWebview


class FakeBackend:
    def __init__(self) -> None:
        self.presses: dict[str, Callable[[], None]] = {}
        self.taken: set[str] = set()
        self.closed = False

    def register(self, hotkey: Hotkey, on_press: Callable[[], None]) -> object:
        if hotkey.name in self.taken:
            raise OSError("Hot key is already registered")
        self.presses[hotkey.name] = on_press
        return hotkey.name

    def unregister(self, handle: object) -> None:
        self.presses.pop(str(handle))

    def close(self) -> None:
        self.closed = True


# ----- parsing ----------------------------------------------------------------------------------


def test_a_hotkey_is_normalised() -> None:
    parsed = parse_hotkey(" Alt + Ctrl + Space ")

    assert parsed.name == "ctrl+alt+space"
    assert parsed.modifiers == MOD_CONTROL | MOD_ALT
    assert parsed.key == 0x20


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("ctrl+a", 0x41),
        ("ctrl+5", 0x35),
        ("win+f12", 0x7B),
        ("alt+escape", 0x1B),
        ("ctrl+left", 0x25),
    ],
)
def test_keys(text: str, key: int) -> None:
    assert parse_hotkey(text).key == key


def test_win_and_aliases() -> None:
    assert parse_hotkey("super+shift+return").name == "shift+win+enter"
    assert parse_hotkey("meta+h").modifiers == MOD_WIN


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "space",
        "a",
        "shift+a",
        "ctrl+",
        "ctrl+ctrl+a",
        "ctrl+alt",
        "ctrl+f25",
        "ctrl+nope",
        "hyper+a",
        "ctrl++a",
        5,
        None,
    ],
)
def test_bad_hotkeys_are_refused(text: object) -> None:
    with pytest.raises(ValueError, match=r"hotkey|modifier|key|needs|repeated"):
        parse_hotkey(text)


# ----- the rules --------------------------------------------------------------------------------


def make() -> tuple[Hotkeys, FakeBackend, list[str]]:
    told: list[str] = []
    backend = FakeBackend()
    return Hotkeys(told.append, backend), backend, told


def test_a_press_runs_the_handler_and_tells_the_page() -> None:
    hotkeys, backend, told = make()
    pressed: list[int] = []

    assert hotkeys.register("ctrl+alt+space", lambda: pressed.append(1)) == "ctrl+alt+space"
    backend.presses["ctrl+alt+space"]()

    assert pressed == [1]
    assert told == ["ctrl+alt+space"]


def test_a_handler_that_raises_still_tells_the_page() -> None:
    hotkeys, backend, told = make()

    def boom() -> None:
        raise RuntimeError("x")

    hotkeys.register("ctrl+alt+b", boom)
    backend.presses["ctrl+alt+b"]()

    assert told == ["ctrl+alt+b"]


def test_a_press_without_a_handler_only_tells_the_page() -> None:
    hotkeys, backend, told = make()

    hotkeys.register("ctrl+alt+n")
    backend.presses["ctrl+alt+n"]()

    assert told == ["ctrl+alt+n"]


def test_a_duplicate_is_refused_even_spelled_differently() -> None:
    hotkeys, _, _ = make()
    hotkeys.register("ctrl+alt+space")

    with pytest.raises(ValueError, match="already registered"):
        hotkeys.register("Alt+Ctrl+Space")


def test_a_shortcut_another_program_holds_is_a_clear_error() -> None:
    hotkeys, backend, _ = make()
    backend.taken.add("ctrl+alt+space")

    with pytest.raises(RuntimeError, match="another program"):
        hotkeys.register("ctrl+alt+space")
    assert hotkeys.registered() == []


def test_unregister() -> None:
    hotkeys, backend, _ = make()
    hotkeys.register("ctrl+alt+space")

    assert hotkeys.unregister("Alt+Ctrl+space") is True
    assert hotkeys.unregister("ctrl+alt+space") is False
    assert backend.presses == {}


def test_close_removes_everything_and_is_repeatable() -> None:
    hotkeys, backend, _ = make()
    hotkeys.register("ctrl+alt+space")

    hotkeys.close()
    hotkeys.close()

    assert backend.closed
    assert hotkeys.registered() == []


@pytest.mark.skipif(sys.platform == "win32", reason="checks the refusal on other systems")
def test_the_real_backend_needs_windows() -> None:
    with pytest.raises(RuntimeError, match="only work on Windows"):
        Win32Hotkeys()


# ----- the shell --------------------------------------------------------------------------------


def test_the_shell_tells_the_page_and_toggles(monkeypatch: pytest.MonkeyPatch) -> None:
    shell = Shell(window=None)
    backend = FakeBackend()
    shell._hotkeys._backend = backend
    sent: list[tuple[str, object]] = []
    window = shell.app.state.window
    monkeypatch.setattr(window, "notify", lambda event, detail=None: sent.append((event, detail)))

    shell.register_hotkey("ctrl+alt+space", shell.toggle_window)
    backend.presses["ctrl+alt+space"]()

    assert sent == [("hotkey", {"hotkey": "ctrl+alt+space"})]
    assert window._hidden is True
    assert shell.hotkeys == ["ctrl+alt+space"]
    assert shell.unregister_hotkey("ctrl+alt+space") is True
    shell.stop()
    assert backend.closed


def test_the_simulated_window_toggles() -> None:
    window = SimulatedWindow("x")

    window.toggle()
    window.toggle()

    assert window._hidden is False


# ----- the native window ------------------------------------------------------------------------


def test_toggle_hides_then_shows(monkeypatch: pytest.MonkeyPatch) -> None:
    webview = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(window_module, "bring_to_front", lambda window: None)
    window, controller = create_native_window(webview, "http://x", Window(), lambda error: None)

    controller.toggle()
    controller.toggle()

    assert window.calls[-2:] == ["hide", "show"]
