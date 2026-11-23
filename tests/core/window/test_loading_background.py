import sys
from pathlib import Path

import pytest

from cornea import Colour, Html, Loading, Shell, Static, Window
from cornea.core import shell as shell_module
from cornea.core.window import loading as loading_module
from cornea.core.window import window as window_module
from cornea.core.window.loading import render_loading, splash_background
from cornea.core.window.theme import system_prefers_dark
from window_fakes import FakeWebview

# ----- Colour ---------------------------------------------------------------------------------


def test_a_colour_is_widened_lowercased_and_prints_as_hex() -> None:
    assert Colour("#ABC").hex == "#aabbcc"
    assert str(Colour("#0D1117")) == "#0d1117"
    assert Colour.rgb(13, 17, 23) == Colour.DARK


@pytest.mark.parametrize("value", ["red", "#12", "#1234567", "rgb(1,2,3)", "#ggg", ""])
def test_a_colour_must_be_hex(value: str) -> None:
    with pytest.raises(ValueError, match="colour looks like"):
        Colour(value)


@pytest.mark.parametrize("parts", [(256, 0, 0), (0, -1, 0)])
def test_rgb_parts_are_checked(parts: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError, match="0 to 255"):
        Colour.rgb(*parts)


def test_the_window_background_takes_hex_text_or_a_colour() -> None:
    assert Window(background="#FFF").background == Colour("#ffffff")
    assert Window(background=Colour.DARK).background == Colour.DARK
    assert Window().background is None
    with pytest.raises(ValueError, match="colour looks like"):
        Window(background="red")


def test_the_loading_page_accepts_a_colour() -> None:
    page = render_loading(Loading(background=Colour.DARK, foreground=Colour("#fff")), Window())

    assert "--custom-bg: #0d1117;" in page
    assert "--custom-fg: #ffffff;" in page


# ----- the colour of the window ---------------------------------------------------------------


def test_the_window_background_wins() -> None:
    assert splash_background(Loading(background="#101010"), Window(background="#222")) == "#222222"


def test_the_loading_background_colours_the_window() -> None:
    assert splash_background(Loading(background="#ABCDEF"), Window()) == "#abcdef"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_set_theme_picks_its_colour(theme: str) -> None:
    expected = {"light": "#ffffff", "dark": "#0d1117"}[theme]

    assert splash_background(Loading(theme=theme), Window()) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(("dark", "expected"), [(True, "#0d1117"), (False, "#ffffff")])
def test_auto_follows_the_system(
    monkeypatch: pytest.MonkeyPatch, dark: bool, expected: str
) -> None:
    monkeypatch.setattr(loading_module, "system_prefers_dark", lambda: dark)

    assert splash_background(Loading(), Window()) == expected


def test_a_colour_name_falls_back_to_the_theme() -> None:
    assert splash_background(Loading(background="red", theme="dark"), Window()) == "#0d1117"


def test_a_replaced_page_leaves_the_window_alone() -> None:
    assert splash_background(Loading(html="<p>x</p>"), Window()) is None
    assert splash_background(None, Window()) is None


# ----- the system's mode ----------------------------------------------------------------------


def test_the_system_mode_is_light_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    assert system_prefers_dark() is False


@pytest.mark.skipif(sys.platform != "win32", reason="reads the Windows registry")
def test_the_system_mode_can_be_read() -> None:
    assert isinstance(system_prefers_dark(), bool)


# ----- the native window ----------------------------------------------------------------------


@pytest.fixture
def webview(monkeypatch: pytest.MonkeyPatch) -> FakeWebview:
    fake = FakeWebview()
    monkeypatch.setattr(shell_module, "require_windows", lambda: None)
    monkeypatch.setattr(shell_module, "require_webview2", lambda: None)
    monkeypatch.setattr(shell_module, "load_webview", lambda: fake)
    monkeypatch.setattr(window_module, "_invoke", lambda native, function: function())
    return fake


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>x</html>", encoding="utf-8")
    return tmp_path


def test_the_window_opens_in_the_loading_colour(webview: FakeWebview, bundle: Path) -> None:
    Shell(Static(bundle), loading=Loading(theme="dark", min_display=0)).run()

    assert webview.windows[0].options["background_color"] == "#0d1117"


def test_the_window_background_is_used_without_a_loading_screen(
    webview: FakeWebview, bundle: Path
) -> None:
    Shell(Static(bundle), window=Window(background=Colour.DARK), loading=None).run()

    assert webview.windows[0].options["background_color"] == "#0d1117"


def test_no_colour_is_passed_when_none_is_known(webview: FakeWebview, bundle: Path) -> None:
    Shell(Static(bundle), loading=None).run()

    assert "background_color" not in webview.windows[0].options


# ----- the footer -----------------------------------------------------------------------------


def test_the_footer_text_is_escaped() -> None:
    page = render_loading(Loading(footer="Acme <b>& Co</b>"), Window())

    assert "<footer>Acme &lt;b&gt;&amp; Co&lt;/b&gt;</footer>" in page


def test_html_in_the_footer_is_kept() -> None:
    page = render_loading(Loading(footer=Html("by <b>Acme</b>")), Window())

    assert "<footer>by <b>Acme</b></footer>" in page


@pytest.mark.parametrize("footer", [None, "", "  "])
def test_no_footer_means_no_element(footer: str | None) -> None:
    assert "<footer" not in render_loading(Loading(footer=footer), Window())
