import http.client
import json
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from asgi_client import AsgiClient
from cornea import Shell, Static, Url, Window, create_app
from cornea.core import window as window_module
from cornea.core.app import allow_host
from cornea.core.window import (
    NativeWindow,
    WindowController,
    apply_webview_settings,
    load_webview,
    require_webview2,
    require_windows,
)


class FakeEvent:
    def __init__(self) -> None:
        self.handlers: list[Callable[[], None]] = []

    def __iadd__(self, handler: Callable[[], None]) -> "FakeEvent":
        self.handlers.append(handler)
        return self

    def fire(self) -> None:
        for handler in list(self.handlers):
            handler()


class FakeWebViewOptions:
    """Remembers what was set; can be told to fail."""

    fail = False

    def __setattr__(self, name: str, value: object) -> None:
        if FakeWebViewOptions.fail:
            raise RuntimeError("settings not available")
        super().__setattr__(name, value)


class FakeWindow:
    def __init__(self, title: str, url: str, **options: Any) -> None:
        self.title = title
        self.url = url
        self.options = options
        self.calls: list[str] = []
        self.options_object = FakeWebViewOptions()
        self.events = SimpleNamespace(
            maximized=FakeEvent(),
            minimized=FakeEvent(),
            restored=FakeEvent(),
            loaded=FakeEvent(),
            closed=FakeEvent(),
        )
        core = SimpleNamespace(Settings=self.options_object)
        self.native = SimpleNamespace(webview=SimpleNamespace(CoreWebView2=core))

    def minimize(self) -> None:
        self.calls.append("minimize")

    def maximize(self) -> None:
        self.calls.append("maximize")

    def restore(self) -> None:
        self.calls.append("restore")

    def destroy(self) -> None:
        self.calls.append("destroy")

    def set_title(self, title: str) -> None:
        self.calls.append(f"title:{title}")


class FakeWebview(ModuleType):
    """Stands in for pywebview: records what is asked and shows no window."""

    def __init__(self) -> None:
        super().__init__("webview")
        self.settings: dict[str, Any] = {"OPEN_DEVTOOLS_IN_DEBUG": True}
        self.windows: list[FakeWindow] = []
        self.start_options: dict[str, Any] = {}
        self.while_open: Callable[[FakeWindow], None] = lambda window: None

    def create_window(self, title: str, url: str, **options: Any) -> FakeWindow:
        window = FakeWindow(title, url, **options)
        self.windows.append(window)
        return window

    def start(self, **options: Any) -> None:
        self.start_options = options
        for window in self.windows:
            window.events.loaded.fire()
            self.while_open(window)


@pytest.fixture
def webview(monkeypatch: pytest.MonkeyPatch) -> FakeWebview:
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(window_module, "_registry_version", lambda: "130.0.1")
    monkeypatch.setattr(window_module, "_invoke", lambda native, function: function())
    monkeypatch.setattr(window_module, "CLOSE_DELAY", 0)
    FakeWebViewOptions.fail = False
    return fake


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    return tmp_path


def request(
    shell: Shell, method: str, path: str, *, cookie: str = "", body: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    headers = {"Origin": shell.base_url, "Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    try:
        connection.request(
            method, path, body=json.dumps(body) if body is not None else None, headers=headers
        )
        response = connection.getresponse()
        text = response.read().decode()
        return response.status, json.loads(text) if text else {}
    finally:
        connection.close()


def sign_in(shell: Shell) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    try:
        connection.request("GET", f"/?cornea_token={shell.app.state.bootstrap_token}")
        return (connection.getresponse().getheader("Set-Cookie") or "").split(";")[0]
    finally:
        connection.close()


# ----- the environment ------------------------------------------------------------------------


def test_windows_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window_module, "sys", SimpleNamespace(platform="linux"))

    with pytest.raises(RuntimeError, match="only work on Windows"):
        require_windows()


def test_webview2_version_is_returned(webview: FakeWebview) -> None:
    assert require_webview2() == "130.0.1"


def test_missing_webview2_says_where_to_get_it(
    webview: FakeWebview, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(window_module, "_registry_version", lambda: None)

    with pytest.raises(RuntimeError, match="WebView2 runtime is not installed") as caught:
        require_webview2()

    assert "developer.microsoft.com" in str(caught.value)


@pytest.mark.skipif(sys.platform != "win32", reason="reads the Windows registry")
def test_registry_lookup_returns_a_version_or_none() -> None:
    version = window_module._registry_version()

    assert version is None or version[0].isdigit()


def test_pywebview_missing_gives_a_reinstall_hint(
    webview: FakeWebview, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert load_webview() is webview
    monkeypatch.setitem(sys.modules, "webview", None)

    with pytest.raises(RuntimeError, match="pywebview is not installed"):
        load_webview()


def test_invoke_runs_on_the_ui_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    class Func:
        def __class_getitem__(cls, item: object) -> Callable[[Callable[[], None]], str]:
            return lambda function: f"wrapped:{function.__name__}"

    sent: list[str] = []
    native = SimpleNamespace(Invoke=sent.append)
    monkeypatch.setitem(sys.modules, "System", SimpleNamespace(Func=Func, Type=object))

    def on_ui_thread() -> None: ...

    window_module._invoke(native, on_ui_thread)

    assert sent == ["wrapped:on_ui_thread"]


# ----- controlling the window -----------------------------------------------------------------


def make_controller(title: str = "App") -> tuple[NativeWindow, FakeWindow]:
    fake = FakeWindow(title, "http://x")
    return NativeWindow(fake, Window(title=title)), fake


def test_controller_passes_calls_to_the_window() -> None:
    controller, fake = make_controller()

    controller.minimize()
    controller.maximize()
    controller.restore()
    controller.set_title("New")

    assert fake.calls == ["minimize", "maximize", "restore", "title:New"]


def test_close_happens_after_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window_module, "CLOSE_DELAY", 0)
    controller, fake = make_controller()

    controller.close()
    time.sleep(0.2)

    assert fake.calls == ["destroy"]


def test_state_follows_the_window_events() -> None:
    controller, fake = make_controller("Main")
    idle = {
        "title": "Main",
        "maximized": False,
        "minimized": False,
        "closed": False,
        "frameless": False,
    }
    assert controller.state() == idle

    fake.events.maximized.fire()
    assert controller.state()["maximized"] is True
    fake.events.minimized.fire()
    assert controller.state() == {**idle, "maximized": True, "minimized": True}
    fake.events.restored.fire()
    assert controller.state() == idle

    controller.set_title("Other")
    assert controller.state()["title"] == "Other"
    fake.events.closed.fire()
    assert controller.state()["closed"] is True


def test_the_native_window_fits_the_controller_protocol() -> None:
    controller: WindowController = make_controller()[0]

    assert controller.state()["title"] == "App"


# ----- narrowing the WebView2 settings --------------------------------------------------------


@pytest.mark.parametrize(
    ("window", "menu", "tools", "status"),
    [
        (Window(), False, False, False),
        (Window(context_menu=True), True, False, False),
        (Window(devtools=True), False, True, False),
        (Window(context_menu=True, devtools=True), True, True, False),
        (Window(debug=True), True, True, True),
    ],
)
def test_each_tool_is_set_to_exactly_what_was_asked(
    window: Window, menu: bool, tools: bool, status: bool, webview: FakeWebview
) -> None:
    fake = FakeWindow("t", "u")

    apply_webview_settings(fake, window)

    options = fake.options_object
    assert options.AreDefaultContextMenusEnabled is menu  # type: ignore[attr-defined]
    assert options.AreDevToolsEnabled is tools  # type: ignore[attr-defined]
    assert options.AreBrowserAcceleratorKeysEnabled is tools  # type: ignore[attr-defined]
    assert options.IsStatusBarEnabled is status  # type: ignore[attr-defined]


# ----- Shell.run with a window ----------------------------------------------------------------


def test_run_shows_a_window_on_the_signed_in_url(webview: FakeWebview, bundle: Path) -> None:
    shell = Shell(
        Static(bundle),
        window=Window(
            title="My App",
            size=(900, 600),
            min_size=(300, 200),
            position=(10, 20),
            frameless=True,
            resizable=False,
            on_top=True,
        ),
    )
    seen: dict[str, Any] = {}

    def while_open(window: FakeWindow) -> None:
        seen["running"] = shell.running
        seen["url"] = shell.url

    webview.while_open = while_open
    shell.run()

    window = webview.windows[0]
    assert (window.title, window.url) == ("My App", seen["url"])
    assert window.options == {
        "width": 900,
        "height": 600,
        "x": 10,
        "y": 20,
        "min_size": (300, 200),
        "resizable": False,
        "frameless": True,
        "on_top": True,
        "easy_drag": False,
    }
    assert seen["running"]
    assert not shell.running


def test_run_leaves_the_position_to_the_system(webview: FakeWebview, bundle: Path) -> None:
    Shell(Static(bundle)).run()

    assert webview.windows[0].options["x"] is None
    assert webview.windows[0].options["y"] is None


def test_the_window_uses_the_edge_engine_in_private_mode(
    webview: FakeWebview, bundle: Path
) -> None:
    Shell(Static(bundle)).run()

    assert webview.start_options["gui"] == "edgechromium"
    assert webview.start_options["private_mode"] is True
    assert webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] is False


@pytest.mark.parametrize(
    ("window", "debug"),
    [
        (Window(), False),
        (Window(context_menu=True), True),
        (Window(devtools=True), True),
        (Window(debug=True), True),
    ],
)
def test_debug_mode_is_on_only_when_a_tool_is_wanted(
    window: Window, debug: bool, webview: FakeWebview, bundle: Path
) -> None:
    Shell(Static(bundle), window=window).run()

    assert webview.start_options["debug"] is debug


def test_the_page_can_control_the_window_over_http(webview: FakeWebview, bundle: Path) -> None:
    shell = Shell(Static(bundle))
    results: dict[str, Any] = {}

    def while_open(window: FakeWindow) -> None:
        cookie = sign_in(shell)
        results["state"] = request(shell, "GET", "/api/window", cookie=cookie)
        for action in ("minimize", "maximize", "restore"):
            results[action] = request(shell, "POST", f"/api/window/{action}", cookie=cookie)
        results["title"] = request(
            shell, "POST", "/api/window/title", cookie=cookie, body={"title": "Renamed"}
        )
        results["empty"] = request(
            shell, "POST", "/api/window/title", cookie=cookie, body={"title": ""}
        )
        results["close"] = request(shell, "POST", "/api/window/close", cookie=cookie)
        results["anonymous"] = request(shell, "POST", "/api/window/minimize")
        time.sleep(0.2)

    webview.while_open = while_open
    shell.run()

    assert results["state"] == (
        200,
        {
            "title": "Cornea Shell",
            "maximized": False,
            "minimized": False,
            "closed": False,
            "frameless": False,
        },
    )
    for action in ("minimize", "maximize", "restore", "title", "close"):
        assert results[action] == (200, {"ok": True})
    assert results["empty"][0] == 422
    assert results["anonymous"][0] == 401
    assert webview.windows[0].calls == [
        "minimize",
        "maximize",
        "restore",
        "title:Renamed",
        "destroy",
    ]


def test_window_routes_without_a_window_answer_409() -> None:
    app = create_app()
    allow_host(app, "127.0.0.1:8000")
    client = AsgiClient(app)
    cookie = (
        client.request("/", query=f"cornea_token={app.state.bootstrap_token}").header("set-cookie")
        or ""
    ).split(";")[0]

    response = client.request(
        "/api/window/minimize", method="POST", cookie=cookie, origin="http://127.0.0.1:8000"
    )

    assert response.status == 409
    assert b"no window" in response.body


def test_failing_to_narrow_the_settings_closes_the_window(
    webview: FakeWebview, bundle: Path
) -> None:
    FakeWebViewOptions.fail = True
    shell = Shell(Static(bundle), window=Window(devtools=True))

    with pytest.raises(RuntimeError, match="could not be set up") as caught:
        shell.run()

    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "destroy" in webview.windows[0].calls
    assert not shell.running


def test_nothing_starts_when_webview2_is_missing(
    webview: FakeWebview, bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(window_module, "_registry_version", lambda: None)
    shell = Shell(Static(bundle))

    with pytest.raises(RuntimeError, match="WebView2"):
        shell.run()

    assert not shell.running
    assert webview.windows == []


def test_nothing_starts_without_pywebview(bundle: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window_module, "_registry_version", lambda: "130.0.1")
    monkeypatch.setitem(sys.modules, "webview", None)
    shell = Shell(Static(bundle))

    with pytest.raises(RuntimeError, match="pywebview is not installed"):
        shell.run()

    assert not shell.running


def test_other_platforms_get_a_clear_error(bundle: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window_module, "sys", SimpleNamespace(platform="linux"))
    shell = Shell(Static(bundle))

    with pytest.raises(RuntimeError, match="only work on Windows"):
        shell.run()

    assert not shell.running


def test_without_a_window_nothing_is_needed(bundle: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "webview", None)
    monkeypatch.setattr(window_module, "_registry_version", lambda: None)
    shell = Shell(Static(bundle), window=None)
    threading.Timer(0.3, shell.stop).start()

    shell.run()

    assert not shell.running


# ----- a direct Url source --------------------------------------------------------------------


def test_a_direct_url_opens_the_address_without_a_server(webview: FakeWebview) -> None:
    shell = Shell(Url("http://localhost:5173"), window=Window(title="Dev", size=(800, 500)))

    shell.run()

    window = webview.windows[0]
    assert (window.title, window.url) == ("Dev", "http://localhost:5173")
    assert (window.options["width"], window.options["height"]) == (800, 500)
    assert window.options["frameless"] is False
    assert not shell.running
    assert shell._socket is None


def test_a_url_string_is_a_direct_source(webview: FakeWebview) -> None:
    Shell("http://localhost:5173").run()

    assert webview.windows[0].url == "http://localhost:5173"


def test_a_direct_url_still_gets_the_window_tools_narrowed(webview: FakeWebview) -> None:
    Shell(Url("http://localhost:5173"), window=Window(devtools=True)).run()

    options = webview.windows[0].options_object
    assert options.AreDevToolsEnabled is True  # type: ignore[attr-defined]
    assert options.AreDefaultContextMenusEnabled is False  # type: ignore[attr-defined]
    assert webview.start_options["debug"] is True


def test_a_direct_url_has_no_local_server() -> None:
    shell = Shell(Url("http://localhost:5173"))

    assert shell.url == "http://localhost:5173"
    for action in (shell.start, lambda: shell.port, lambda: shell.base_url):
        with pytest.raises(RuntimeError, match="no local server"):
            action()


def test_a_direct_url_cannot_be_frameless() -> None:
    with pytest.raises(ValueError, match="frameless"):
        Shell(Url("http://localhost:5173"), window=Window(frameless=True))


def test_a_direct_url_needs_a_window() -> None:
    with pytest.raises(ValueError, match="needs a window"):
        Shell(Url("http://localhost:5173"), window=None)


def test_a_direct_url_still_checks_the_environment(
    webview: FakeWebview, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(window_module, "_registry_version", lambda: None)

    with pytest.raises(RuntimeError, match="WebView2"):
        Shell(Url("http://localhost:5173")).run()

    assert webview.windows == []


def test_the_state_says_whether_the_window_is_frameless() -> None:
    plain = NativeWindow(FakeWindow("t", "u"), Window())
    frameless = NativeWindow(FakeWindow("t", "u"), Window(frameless=True))

    assert plain.state()["frameless"] is False
    assert frameless.state()["frameless"] is True
