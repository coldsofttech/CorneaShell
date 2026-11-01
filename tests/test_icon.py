from pathlib import Path

import pytest

from cornea import Shell, Static, Window
from cornea.core import window as window_module
from cornea.core.window import create_native_window
from test_window import FakeWebview

ICON = Path(__file__).resolve().parent.parent / "examples" / "static_html" / "icon.png"


@pytest.mark.parametrize("name", ["a.ico", "a.PNG", "a.bmp", "a.gif", "a.jpg", "a.jpeg"])
def test_icon_types_are_accepted(name: str) -> None:
    assert Window(icon=name).icon == name


@pytest.mark.parametrize("name", ["a.svg", "a.txt", "icon"])
def test_other_types_are_refused(name: str) -> None:
    with pytest.raises(ValueError, match="icon must be one of"):
        Window(icon=name)


def test_the_icon_is_applied_once_when_the_window_shows(monkeypatch: pytest.MonkeyPatch) -> None:
    applied: list[Path] = []
    monkeypatch.setattr(window_module, "apply_icon", lambda window, path: applied.append(path))
    window, _ = create_native_window(FakeWebview(), "http://x", Window(icon=ICON), lambda e: None)

    window.events.shown.fire()
    window.events.loaded.fire()

    assert applied == [ICON.resolve()]


def test_a_failed_icon_is_retried_then_only_warned(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fail(window: object, path: Path) -> None:
        raise RuntimeError("no UI yet")

    monkeypatch.setattr(window_module, "apply_icon", fail)
    window, _ = create_native_window(FakeWebview(), "http://x", Window(icon=ICON), lambda e: None)

    window.events.shown.fire()  # must not raise
    window.events.loaded.fire()

    assert caplog.text.count("Could not set the window icon") == 2


def test_no_icon_means_no_listeners() -> None:
    window, _ = create_native_window(FakeWebview(), "http://x", Window(), lambda e: None)

    assert not window.events.shown.handlers


def test_a_missing_icon_file_stops_the_run_before_anything_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    monkeypatch.setattr(window_module, "_registry_version", lambda: "1")
    monkeypatch.setitem(__import__("sys").modules, "webview", object())
    shell = Shell(Static(tmp_path), window=Window(icon=tmp_path / "missing.png"))

    with pytest.raises(FileNotFoundError, match="window icon not found"):
        shell.run()

    assert not shell.running
