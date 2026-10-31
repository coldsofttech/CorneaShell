import asyncio
import http.client
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cornea import Bridge, Shell, Static, Window, create_app
from cornea.core import bridge as bridge_module
from cornea.core.bridge import ActionRegistry, BadArguments, UnknownAction
from cornea.core.window import NativeWindow, SimulatedWindow, Unavailable


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    return tmp_path


class FakeDialogs:
    """A window whose dialogs return what the test says, and remember how they were asked."""

    headless = False

    def __init__(self, answer: list[str] | None = None) -> None:
        self.answer = answer
        self.asked: list[dict[str, Any]] = []

    def dialog(self, kind: str, **options: Any) -> list[str] | None:
        self.asked.append({"kind": kind, **options})
        return self.answer


COOKIES: dict[str, str] = {}


def session_cookie(shell: Shell) -> str:
    """Sign in once per shell: the start-up token can only be used once."""
    token = shell.app.state.bootstrap_token
    if token not in COOKIES:
        connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
        connection.request("GET", f"/?cornea_token={token}")
        COOKIES[token] = (connection.getresponse().getheader("Set-Cookie") or "").split(";")[0]
        connection.close()
    return COOKIES[token]


def call(
    shell: Shell,
    action: str,
    body: dict[str, Any] | None = None,
    *,
    method: str = "POST",
) -> tuple[int, dict[str, Any]]:
    headers = {
        "Origin": shell.base_url,
        "Content-Type": "application/json",
        "Cookie": session_cookie(shell),
    }
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    try:
        path = f"/api/bridge/{action}" if action else "/api/bridge"
        connection.request(
            method, path, body=json.dumps(body) if body is not None else None, headers=headers
        )
        response = connection.getresponse()
        text = response.read().decode()
        return response.status, json.loads(text) if text else {}
    finally:
        connection.close()


def fake_browser(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stand in for the system browser and return the addresses it was asked to open."""
    opened: list[str] = []

    def open_url(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr("webbrowser.open", open_url)
    return opened


# ----- the registry ---------------------------------------------------------------------------


def run(registry: ActionRegistry, name: str, arguments: dict[str, Any] | None = None) -> Any:
    return asyncio.run(registry.call(name, arguments or {}, None))


def test_the_five_built_in_actions_are_on_by_default() -> None:
    assert ActionRegistry().names() == [
        "choose_folder",
        "choose_file",
        "save_file",
        "open_external",
        "platform_info",
    ]


def test_built_ins_can_be_switched_off() -> None:
    registry = ActionRegistry(disabled=("open_external", "save_file"))

    assert "open_external" not in registry.names()
    with pytest.raises(UnknownAction):
        run(registry, "open_external", {"url": "https://example.com"})


def test_only_built_ins_can_be_disabled() -> None:
    with pytest.raises(ValueError, match="unknown built-in"):
        ActionRegistry(disabled=("nothing",))


def test_registered_actions_are_listed_after_the_built_ins() -> None:
    registry = ActionRegistry()

    @registry.action("pick_report")
    def pick_report() -> str:
        return "report.pdf"

    assert registry.names()[-1] == "pick_report"
    assert run(registry, "pick_report") == "report.pdf"


def test_register_returns_the_function_unchanged() -> None:
    registry = ActionRegistry()

    def handler() -> None: ...

    assert registry.register("handler", handler) is handler


@pytest.mark.parametrize("name", ["", "Upper", "1start", "has-dash", "has space", "dotted.name"])
def test_action_names_must_be_plain_words(name: str) -> None:
    with pytest.raises(ValueError, match="action names look like"):
        ActionRegistry().register(name, lambda: None)


def test_built_in_names_cannot_be_taken_over() -> None:
    with pytest.raises(ValueError, match="built-in"):
        ActionRegistry().register("platform_info", lambda: None)


def test_a_disabled_built_in_name_is_still_reserved() -> None:
    with pytest.raises(ValueError, match="built-in"):
        ActionRegistry(disabled=("open_external",)).register("open_external", lambda: None)


def test_names_cannot_be_registered_twice() -> None:
    registry = ActionRegistry()
    registry.register("once", lambda: None)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("once", lambda: None)


def test_unregistered_actions_are_rejected() -> None:
    with pytest.raises(UnknownAction):
        run(ActionRegistry(), "delete_everything")


def test_arguments_are_passed_by_name() -> None:
    registry = ActionRegistry()
    registry.register("add", lambda a, b=1: a + b)

    assert run(registry, "add", {"a": 2, "b": 5}) == 7
    assert run(registry, "add", {"a": 2}) == 3


def test_wrong_arguments_are_a_bad_request_not_a_crash() -> None:
    registry = ActionRegistry()
    registry.register("add", lambda a, b=1: a + b)

    with pytest.raises(BadArguments):
        run(registry, "add", {})
    with pytest.raises(BadArguments):
        run(registry, "add", {"a": 1, "extra": 2})


def test_async_actions_are_awaited() -> None:
    registry = ActionRegistry()

    async def slow() -> str:
        await asyncio.sleep(0)
        return "done"

    registry.register("slow", slow)

    assert run(registry, "slow") == "done"


# ----- the built-in actions -------------------------------------------------------------------


def test_choose_folder_returns_the_first_path_or_none() -> None:
    window = FakeDialogs(["C:/data"])

    assert bridge_module.choose_folder(window, directory="C:/") == "C:/data"  # type: ignore[arg-type]
    assert window.asked == [{"kind": "folder", "directory": "C:/"}]
    assert bridge_module.choose_folder(FakeDialogs(None)) is None  # type: ignore[arg-type]


def test_choose_file_passes_the_options_through() -> None:
    window = FakeDialogs(["a.png", "b.png"])

    result = bridge_module.choose_file(
        window,  # type: ignore[arg-type]
        directory="C:/pics",
        file_types=("Images (*.png)",),
        multiple=True,
    )

    assert result == ["a.png", "b.png"]
    assert window.asked == [
        {
            "kind": "open",
            "directory": "C:/pics",
            "file_types": ("Images (*.png)",),
            "multiple": True,
        }
    ]


def test_save_file_only_chooses_a_path() -> None:
    window = FakeDialogs(["C:/out/report.pdf"])

    assert bridge_module.save_file(window, filename="report.pdf") == "C:/out/report.pdf"  # type: ignore[arg-type]
    assert window.asked[0]["kind"] == "save"
    assert window.asked[0]["filename"] == "report.pdf"
    assert bridge_module.save_file(FakeDialogs(None)) is None  # type: ignore[arg-type]


@pytest.mark.parametrize("call_dialog", ["choose_folder", "choose_file", "save_file"])
def test_dialogs_without_a_window_are_unavailable(call_dialog: str) -> None:
    with pytest.raises(Unavailable, match="no window"):
        getattr(bridge_module, call_dialog)(None)


def test_open_external_opens_only_safe_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    opened = fake_browser(monkeypatch)

    for good in ("https://example.com/a?b=1", "http://localhost:3000", " mailto:me@example.com "):
        assert bridge_module.open_external(None, good) == {"opened": True}

    assert opened == ["https://example.com/a?b=1", "http://localhost:3000", "mailto:me@example.com"]


@pytest.mark.parametrize(
    "bad",
    [
        "file:///C:/Windows/System32/calc.exe",
        "javascript:alert(1)",
        "ms-settings:",
        "calc.exe",
        "//example.com",
        "",
        "   ",
        "https://example.com/\nnext",
        "https://example.com/" + "a" * 3000,
        123,
    ],
)
def test_open_external_rejects_everything_else(bad: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("webbrowser.open", lambda url: pytest.fail("opened"))

    with pytest.raises(BadArguments):
        bridge_module.open_external(None, bad)


def test_platform_info_describes_the_system() -> None:
    info = bridge_module.platform_info(SimpleNamespace(headless=False))

    assert info["platform"] == ("windows" if sys.platform == "win32" else sys.platform)
    assert {"release", "version", "python", "cornea", "webview2", "window"} <= set(info)
    assert info["window"] is True
    assert bridge_module.platform_info(SimulatedWindow("t"))["window"] is False
    assert bridge_module.platform_info(None)["window"] is False


# ----- over HTTP, headless --------------------------------------------------------------------


def test_the_page_can_list_the_actions(bundle: Path) -> None:
    with Shell(Static(bundle), window=None) as shell:
        shell.action("pick_report")(lambda: "x")

        status, body = call(shell, "", method="GET")

        assert status == 200
        assert body["actions"][-1] == "pick_report"
        assert "choose_folder" in body["actions"]


def test_platform_info_works_without_a_window(bundle: Path) -> None:
    with Shell(Static(bundle), window=None) as shell:
        status, body = call(shell, "platform_info")

        assert status == 200
        assert body["available"] is True
        assert body["result"]["window"] is False


@pytest.mark.parametrize("dialog", ["choose_folder", "choose_file", "save_file"])
def test_dialogs_answer_unavailable_not_an_error_without_a_window(
    dialog: str, bundle: Path
) -> None:
    with Shell(Static(bundle), window=None) as shell:
        status, body = call(shell, dialog)

        assert status == 200
        assert body["available"] is False
        assert "without one" in body["reason"]


def test_open_external_is_validated_over_http(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = fake_browser(monkeypatch)
    with Shell(Static(bundle), window=None) as shell:
        ok = call(shell, "open_external", {"url": "https://example.com"})
        bad = call(shell, "open_external", {"url": "file:///etc/passwd"})
        missing = call(shell, "open_external", {})

    assert ok == (200, {"available": True, "result": {"opened": True}})
    assert bad[0] == 422
    assert "only http, https and mailto" in bad[1]["error"]
    assert missing[0] == 422
    assert opened == ["https://example.com"]


def test_unknown_actions_are_404(bundle: Path) -> None:
    with Shell(Static(bundle), window=None) as shell:
        status, body = call(shell, "format_disk")

        assert (status, body) == (404, {"error": "Unknown action"})


def test_disabled_built_ins_answer_like_unknown_ones(bundle: Path) -> None:
    with Shell(Static(bundle), window=None, bridge=Bridge(disabled=("open_external",))) as shell:
        assert call(shell, "open_external", {"url": "https://example.com"})[0] == 404
        assert call(shell, "platform_info")[0] == 200
        assert "open_external" not in call(shell, "", method="GET")[1]["actions"]


def test_the_hosts_own_actions_are_called_over_http(bundle: Path) -> None:
    shell = Shell(Static(bundle), window=None)

    @shell.action("pick_report")
    def pick_report(year: int, title: str = "Report") -> dict[str, Any]:
        return {"file": f"{title}-{year}.pdf"}

    with shell:
        status, body = call(shell, "pick_report", {"year": 2024})

        assert (status, body) == (200, {"available": True, "result": {"file": "Report-2024.pdf"}})
        assert call(shell, "pick_report", {})[0] == 422
        assert call(shell, "pick_report", {"year": 1, "bogus": 2})[0] == 422


def test_actions_can_be_called_without_a_body(bundle: Path) -> None:
    shell = Shell(Static(bundle), window=None)
    shell.action("ping")(lambda: "pong")

    with shell:
        assert call(shell, "ping")[1]["result"] == "pong"


def test_a_value_error_from_an_action_is_a_bad_request(bundle: Path) -> None:
    shell = Shell(Static(bundle), window=None)

    @shell.action("strict")
    def strict() -> None:
        raise ValueError("year must be positive")

    with shell:
        assert call(shell, "strict") == (422, {"error": "year must be positive"})


def test_a_crash_in_an_action_is_logged_but_not_shown(
    bundle: Path, caplog: pytest.LogCaptureFixture
) -> None:
    shell = Shell(Static(bundle), window=None)

    @shell.action("crash")
    def crash() -> None:
        raise RuntimeError("secret path C:/Users/someone")

    with shell, caplog.at_level(logging.ERROR, logger="cornea.core.bridge_routes"):
        status, body = call(shell, "crash")

    assert (status, body) == (500, {"error": "The action failed"})
    assert "secret path" not in json.dumps(body)
    assert "secret path" in caplog.text


def test_async_actions_work_over_http(bundle: Path) -> None:
    shell = Shell(Static(bundle), window=None)

    @shell.action("later")
    async def later() -> list[int]:
        return [1, 2]

    with shell:
        assert call(shell, "later")[1]["result"] == [1, 2]


def raw_post(shell: Shell, headers: dict[str, str]) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    try:
        connection.request("POST", "/api/bridge/platform_info", headers=headers)
        return connection.getresponse().status
    finally:
        connection.close()


def test_the_bridge_needs_a_session_and_an_origin(bundle: Path) -> None:
    with Shell(Static(bundle), window=None) as shell:
        cookie = session_cookie(shell)

        assert raw_post(shell, {"Origin": shell.base_url}) == 401
        assert raw_post(shell, {"Cookie": cookie}) == 403
        assert raw_post(shell, {"Cookie": cookie, "Origin": "http://evil.example"}) == 403
        assert raw_post(shell, {"Cookie": cookie, "Origin": shell.base_url}) == 200


def test_the_hosts_routers_cannot_shadow_the_bridge(bundle: Path) -> None:
    from fastapi import APIRouter

    router = APIRouter()

    @router.post("/bridge/platform_info")
    def fake() -> dict[str, str]:
        return {"fake": "yes"}

    shell = Shell(Static(bundle), routers=[router], window=None)
    with shell:
        assert call(shell, "platform_info")[1]["available"] is True


def test_the_bridge_without_a_window_object_says_unavailable() -> None:
    from asgi_client import AsgiClient
    from cornea.core.app import allow_host

    app = create_app()
    allow_host(app, "127.0.0.1:8000")
    client = AsgiClient(app)
    cookie = (
        client.request("/", query=f"cornea_token={app.state.bootstrap_token}").header("set-cookie")
        or ""
    ).split(";")[0]

    response = client.request(
        "/api/bridge/choose_folder",
        method="POST",
        cookie=cookie,
        origin="http://127.0.0.1:8000",
    )

    assert response.status == 200
    assert json.loads(response.body)["available"] is False


# ----- dialogs through a real-looking window --------------------------------------------------


def test_dialogs_reach_the_window_over_http(bundle: Path) -> None:
    shell = Shell(Static(bundle), window=None)
    dialogs = FakeDialogs(["C:/chosen"])
    shell.app.state.window = dialogs

    with shell:
        status, body = call(shell, "choose_folder", {"directory": "C:/start"})

        assert (status, body) == (200, {"available": True, "result": "C:/chosen"})
        assert dialogs.asked == [{"kind": "folder", "directory": "C:/start"}]
        assert call(shell, "platform_info")[1]["result"]["window"] is True


def test_a_cancelled_dialog_is_a_null_result(bundle: Path) -> None:
    shell = Shell(Static(bundle), window=None)
    shell.app.state.window = FakeDialogs(None)

    with shell:
        assert call(shell, "choose_file")[1] == {"available": True, "result": None}


def test_a_bad_dialog_option_is_a_bad_request(bundle: Path) -> None:
    class Strict(FakeDialogs):
        def dialog(self, kind: str, **options: Any) -> list[str] | None:
            raise ValueError("bad file type")

    shell = Shell(Static(bundle), window=None)
    shell.app.state.window = Strict()

    with shell:
        assert call(shell, "choose_file", {"file_types": ["nonsense"]}) == (
            422,
            {"error": "bad file type"},
        )


# ----- the native window's dialogs ------------------------------------------------------------


class FakeFileDialog:
    OPEN, FOLDER, SAVE = "open", "folder", "save"


class FakeNativeWindow:
    def __init__(self, answer: Sequence[str] | None) -> None:
        self.answer = answer
        self.calls: list[tuple[Any, dict[str, Any]]] = []
        self.events = SimpleNamespace(
            maximized=_Event(), minimized=_Event(), restored=_Event(), closed=_Event()
        )

    def create_file_dialog(self, kind: Any, **options: Any) -> Sequence[str] | None:
        self.calls.append((kind, options))
        return self.answer


class _Event:
    def __iadd__(self, handler: Any) -> "_Event":
        return self


def native(answer: Sequence[str] | None) -> tuple[NativeWindow, FakeNativeWindow]:
    fake = FakeNativeWindow(answer)
    webview = SimpleNamespace(FileDialog=FakeFileDialog)
    return NativeWindow(fake, Window(), webview), fake  # type: ignore[arg-type]


def test_the_native_window_maps_dialogs_to_pywebview() -> None:
    window, fake = native(("C:/a", "C:/b"))

    result = window.dialog("open", directory="C:/", file_types=["Text (*.txt)"], multiple=True)

    assert result == ["C:/a", "C:/b"]
    assert fake.calls == [
        (
            "open",
            {
                "directory": "C:/",
                "allow_multiple": True,
                "save_filename": "",
                "file_types": ("Text (*.txt)",),
            },
        )
    ]


@pytest.mark.parametrize("kind", ["folder", "open", "save"])
def test_each_dialog_kind_uses_its_pywebview_type(kind: str) -> None:
    window, fake = native(("x",))

    window.dialog(kind)  # type: ignore[arg-type]

    assert fake.calls[0][0] == kind


def test_the_native_window_reports_a_cancelled_dialog_as_none() -> None:
    assert native(None)[0].dialog("folder") is None
    assert native(())[0].dialog("folder") is None


def test_a_native_window_without_pywebview_is_unavailable() -> None:
    window = NativeWindow(FakeNativeWindow(None), Window())

    with pytest.raises(Unavailable):
        window.dialog("folder")


def test_window_kinds_say_whether_they_are_headless() -> None:
    assert native(None)[0].headless is False
    assert SimulatedWindow("t").headless is True
    with pytest.raises(Unavailable):
        SimulatedWindow("t").dialog("open")
