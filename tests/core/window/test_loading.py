from pathlib import Path

import pytest

from cornea import Loading, Shell, Static, Url, Window
from cornea.core import shell as shell_module
from cornea.core.window import window as window_module
from cornea.core.window.loading import check_loading, render_loading
from window_fakes import FakeWebview


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>x</html>", encoding="utf-8")
    return tmp_path


@pytest.fixture
def webview(monkeypatch: pytest.MonkeyPatch) -> FakeWebview:
    fake = FakeWebview()
    monkeypatch.setattr(shell_module, "require_windows", lambda: None)
    monkeypatch.setattr(shell_module, "require_webview2", lambda: None)
    monkeypatch.setattr(shell_module, "load_webview", lambda: fake)
    monkeypatch.setattr(window_module, "_invoke", lambda native, function: function())
    return fake


# ----- the settings ---------------------------------------------------------------------------


def test_the_defaults_name_cornea() -> None:
    loading = Loading()

    assert loading.subtitle == "Shell provided by Cornea"
    assert (loading.title, loading.icon, loading.theme) == (None, None, "auto")


@pytest.mark.parametrize(
    "options",
    [{"theme": "blue"}, {"min_display": -1}, {"icon": "logo.svg"}, {"background": "red;}</style>"}],
)
def test_bad_settings_are_refused(options: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=r"theme|min_display|icon|background"):
        Loading(**options)  # type: ignore[arg-type]


# ----- the page -------------------------------------------------------------------------------


def test_the_page_shows_the_title_and_subtitle_of_the_window() -> None:
    page = render_loading(Loading(subtitle="Hold on"), Window(title="My App"))

    assert "<h1>My App</h1>" in page
    assert "<p>Hold on</p>" in page


def test_text_is_escaped() -> None:
    page = render_loading(Loading(subtitle="<script>x</script>"), Window(title="A & B"))

    assert "<script>" not in page
    assert "A &amp; B" in page


def test_the_page_runs_no_scripts_and_loads_nothing_from_the_network() -> None:
    page = render_loading(Loading(), Window())

    assert "default-src 'none'" in page
    assert "script-src" not in page


def test_the_icon_comes_from_the_window_unless_given(tmp_path: Path) -> None:
    icon = tmp_path / "a.png"
    icon.write_bytes(b"png")

    page = render_loading(Loading(), Window(icon=icon))
    own = render_loading(Loading(icon=icon), Window())

    assert "data:image/png;base64," in page
    assert "data:image/png;base64," in own
    assert "<img" not in render_loading(Loading(), Window())


def test_the_theme_and_colours_are_used() -> None:
    page = render_loading(Loading(theme="dark", background="#101010"), Window())

    assert 'content="dark"' in page
    assert "--custom-bg: #101010;" in page
    assert 'data-theme="dark"' in page


def test_your_own_html_replaces_the_page(tmp_path: Path) -> None:
    file = tmp_path / "wait.html"
    file.write_text("<p>file</p>", encoding="utf-8")

    assert render_loading(Loading(html="<p>inline</p>"), Window()) == "<p>inline</p>"
    assert render_loading(Loading(html=file), Window()) == "<p>file</p>"


def test_a_missing_icon_or_page_is_found_before_anything_starts(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="icon"):
        check_loading(Loading(icon=tmp_path / "none.png"))
    with pytest.raises(FileNotFoundError, match="page"):
        check_loading(Loading(html=tmp_path / "none.html"))


# ----- the start-up order ---------------------------------------------------------------------


def test_the_window_opens_on_the_loading_screen_then_moves_to_the_app(
    bundle: Path, webview: FakeWebview
) -> None:
    seen: list[str] = []
    Shell(Static(bundle), loading=Loading(min_display=0)).run(on_ready=lambda s: seen.append(s.url))

    window = webview.windows[0]
    assert window.url is not None
    assert window.url.startswith("http://127.0.0.1:")
    assert window.options["html"] is not None
    assert window.calls.count(f"load_url:{seen[0]}") == 1


def test_the_loading_screen_is_off_on_request(bundle: Path, webview: FakeWebview) -> None:
    for off in (None, False):
        webview.windows.clear()
        Shell(Static(bundle), loading=off).run()

        assert "html" not in webview.windows[0].options
        assert not any(call.startswith("load_url") for call in webview.windows[0].calls)


def test_there_is_no_loading_screen_without_a_window(bundle: Path) -> None:
    assert Shell(Static(bundle), window=None).loading is None


def test_the_loading_screen_is_not_the_first_page(bundle: Path, webview: FakeWebview) -> None:
    shell = Shell(Static(bundle), loading=Loading(min_display=0), measure=lambda t: None)

    shell.run()

    # The fake fires one load for the loading screen and one for the app.
    assert shell.timings.page_loaded is not None


def test_a_start_that_fails_closes_the_window_and_raises(
    bundle: Path, webview: FakeWebview, monkeypatch: pytest.MonkeyPatch
) -> None:
    shell = Shell(Static(bundle), loading=Loading(min_display=0))

    def fail() -> None:
        raise OSError("port in use")

    monkeypatch.setattr(shell, "_start_app", fail)

    with pytest.raises(OSError, match="port in use"):
        shell.run()

    assert "destroy" in webview.windows[0].calls


def test_a_direct_address_gets_the_loading_screen_too(webview: FakeWebview) -> None:
    address = "http://127.0.0.1:9/"

    Shell(Url(address, mode="direct"), loading=Loading(min_display=0)).run()

    window = webview.windows[0]
    assert window.options["html"] is not None
    assert window.calls.count(f"load_url:{address}") == 1
