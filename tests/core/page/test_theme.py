"""The system theme: reading it, serving it, and telling the page when it changes."""

import sys

import pytest

from cornea import Window
from cornea.core.page import Theme, ThemeWatcher, read_theme
from cornea.core.page.theme import accent_from_abgr, accent_from_argb
from cornea.core.window.window import create_native_window
from window_fakes import FakeWebview


def test_accent_colours_are_converted_from_both_windows_layouts() -> None:
    assert accent_from_abgr(0xFF3366CC) == "#cc6633"
    assert accent_from_argb(0xFF3366CC) == "#3366cc"


def test_without_windows_the_theme_is_light_with_no_accent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    assert read_theme() == Theme("light", None)


def test_the_client_offers_the_theme() -> None:
    from importlib import resources

    source = resources.files("cornea.core").joinpath("client.js").read_text(encoding="utf-8")

    assert 'request("/theme")' in source


def test_the_watcher_reports_only_real_changes() -> None:
    themes = iter([Theme("light", "#111111"), Theme("light", "#111111"), Theme("dark", "#111111")])
    seen: list[Theme] = []
    watcher = ThemeWatcher(seen.append, read=lambda: next(themes))

    assert watcher.check() is False
    assert watcher.check() is True
    assert seen == [Theme("dark", "#111111")]


def test_a_failing_handler_does_not_stop_the_watcher() -> None:
    themes = iter([Theme("light"), Theme("dark")])

    def boom(theme: Theme) -> None:
        raise RuntimeError("page gone")

    watcher = ThemeWatcher(boom, read=lambda: next(themes))

    assert watcher.check() is True


def test_the_window_tells_the_page_when_the_theme_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    webview = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", webview)
    themes = iter([Theme("light"), Theme("dark", "#ff0000")])
    monkeypatch.setattr("cornea.core.page.theme.read_theme", lambda: next(themes))
    scripts: list[str] = []
    window, _ = create_native_window(webview, "http://x", Window(), lambda error: None)
    window.evaluate_js = lambda script: scripts.append(script)
    started = []
    monkeypatch.setattr(ThemeWatcher, "start", lambda self: started.append(self))

    window.events.shown.fire()
    started[0].check()

    assert 'new CustomEvent("cornea:theme-change"' in scripts[0]
    assert '{"mode": "dark", "accent": "#ff0000"}' in scripts[0]
