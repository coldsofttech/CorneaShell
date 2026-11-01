import dataclasses
import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.main import get_command
from typer.testing import CliRunner

from cornea import (
    DEV_CSP,
    App,
    Asgi,
    Bridge,
    Process,
    Security,
    Server,
    Shell,
    Static,
    Timings,
    Url,
    Window,
    Wsgi,
)
from cornea.cli import app, options
from cornea.core import window as window_module

runner = CliRunner()
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Calls:
    """Stands in for run(): remembers how the command called it."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def __call__(self, source: Any = None, **kwargs: Any) -> None:
        self.items.append({"source": source, **kwargs})

    @property
    def last(self) -> dict[str, Any]:
        return self.items[-1]


@pytest.fixture(autouse=True)
def restore_cornea_logging(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Undo configure_logging after each test.

    A command such as ``open --debug`` configures logging for real, and its handler would
    otherwise outlive the test and write to a stream that is already closed.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))  # where debug logs go
    logger = logging.getLogger("cornea")
    level, propagate = logger.level, logger.propagate
    yield
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(level)
    logger.propagate = propagate


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    recorded = Calls()
    monkeypatch.setattr("cornea.cli.commands.run_shell", recorded)
    return recorded


def invoke(*args: str) -> Any:
    return runner.invoke(app, list(args))


# ----- the flags cover every setting ----------------------------------------------------------

FLAGS: dict[type, dict[str, str]] = {
    Server: {"host": "--host", "port": "--port"},
    Security: {
        "allowed_hosts": "--allowed-host",
        "csp": "--csp",
        "api_prefix": "--api-prefix",
        "token_ttl": "--token-ttl",
        "cookie_samesite": "--cookie-samesite",
        "public_paths": "--public-path",
        "require_origin": "--require-origin",
    },
    Window: {
        "title": "--title",
        "size": "--size",
        "min_size": "--min-size",
        "position": "--position",
        "frameless": "--frameless",
        "resizable": "--resizable",
        "on_top": "--on-top",
        "context_menu": "--context-menu",
        "devtools": "--devtools",
        "debug": "--debug",
        "js_api": "--js-api",
        "icon": "--icon",
    },
    Bridge: {"disabled": "--disable-action"},
    App: {
        "id": "--app-id",
        "single_instance": "--single-instance",
        "remember_window": "--remember-window",
    },
    Url: {"url": "--url", "mode": "--mode"},
    Process: {
        "command": "--run",
        "url": "--url",
        "cwd": "--run-cwd",
        "mode": "--mode",
        "timeout": "--run-timeout",
    },
    Static: {
        "path": "--web-dist",
        "package": "--package",
        "package_path": "--package-path",
        "spa": "--spa",
        "hashed_prefixes": "--hashed-prefix",
    },
}


def option_names(command: str) -> set[str]:
    cli: Any = get_command(app)
    return {name for param in cli.commands[command].params for name in param.opts}


@pytest.mark.parametrize("settings", FLAGS, ids=lambda cls: cls.__name__)
def test_every_setting_has_a_flag(settings: type) -> None:
    fields = {field.name for field in dataclasses.fields(settings)}

    # A new setting fails here until it is given a flag and listed above.
    assert fields == set(FLAGS[settings])
    assert set(FLAGS[settings].values()) <= option_names("open")


def test_serve_has_every_flag_except_the_window_ones() -> None:
    window_flags = set(FLAGS[Window].values()) | set(FLAGS[App].values())

    assert option_names("serve") == option_names("open") - window_flags
    assert window_flags <= option_names("open")


def test_the_url_and_app_sources_have_flags() -> None:
    names = option_names("open")

    assert {"--url", "--asgi", "--wsgi", "--app-dir"} <= names
    assert {Url, Asgi, Wsgi}


# ----- open -----------------------------------------------------------------------------------


def test_open_with_a_folder_shows_a_window(calls: Calls) -> None:
    result = invoke("open", "web/dist")

    assert result.exit_code == 0
    assert calls.last["source"] == Static(path=Path("web/dist"))
    assert calls.last["window"] == Window()
    assert calls.last["server"] == Server()
    assert calls.last["security"] == Security()
    assert calls.last["bridge"] == Bridge()
    assert calls.last["on_ready"] is None


def test_open_with_no_source_uses_the_default_lookup(calls: Calls) -> None:
    invoke("open")

    assert calls.last["source"] == Static()


def test_open_maps_every_window_flag(calls: Calls) -> None:
    invoke(
        "open",
        "web/dist",
        "--title",
        "My App",
        "--size",
        "1200x800",
        "--min-size",
        "300x200",
        "--position",
        "-100,50",
        "--frameless",
        "--no-resizable",
        "--on-top",
        "--context-menu",
        "--devtools",
        "--debug",
    )

    assert calls.last["window"] == Window(
        title="My App",
        size=(1200, 800),
        min_size=(300, 200),
        position=(-100, 50),
        frameless=True,
        resizable=False,
        on_top=True,
        context_menu=True,
        devtools=True,
        debug=True,
    )


def test_open_maps_server_security_and_bridge_flags(calls: Calls) -> None:
    invoke(
        "open",
        "web/dist",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
        "--allowed-host",
        "app.local:8765",
        "--allowed-host",
        "other.local",
        "--csp",
        "default-src 'self'",
        "--api-prefix",
        "/v1",
        "--token-ttl",
        "120",
        "--cookie-samesite",
        "lax",
        "--public-path",
        "/health",
        "--public-path",
        "/status",
        "--no-require-origin",
        "--disable-action",
        "open_external",
        "--disable-action",
        "save_file",
    )

    assert calls.last["server"] == Server(host="127.0.0.1", port=8765)
    assert calls.last["security"] == Security(
        allowed_hosts=("app.local:8765", "other.local"),
        csp="default-src 'self'",
        api_prefix="/v1",
        token_ttl=120,
        cookie_samesite="lax",
        public_paths=("/health", "/status"),
        require_origin=False,
    )
    assert calls.last["bridge"] == Bridge(disabled=("open_external", "save_file"))


def test_open_maps_the_bundle_flags(calls: Calls) -> None:
    invoke(
        "open",
        "--package",
        "shipped_ui",
        "--package-path",
        "frontend",
        "--no-spa",
        "--hashed-prefix",
        "static/",
        "--hashed-prefix",
        "fonts/",
    )

    assert calls.last["source"] == Static(
        package="shipped_ui",
        package_path="frontend",
        spa=False,
        hashed_prefixes=("static/", "fonts/"),
    )


def test_open_with_an_address_opens_it_directly(calls: Calls) -> None:
    invoke("open", "http://localhost:5173")
    assert calls.last["source"] == Url("http://localhost:5173")

    invoke("open", "--url", "https://example.com")
    assert calls.last["source"] == Url("https://example.com")


def test_an_address_can_be_proxied(calls: Calls) -> None:
    invoke("open", "http://localhost:5173", "--mode", "proxy")
    assert calls.last["source"] == Url("http://localhost:5173", mode="proxy")

    invoke("open", "--url", "http://localhost:5173", "--mode", "direct")
    assert calls.last["source"] == Url("http://localhost:5173", mode="direct")


def test_a_proxied_address_may_be_frameless(calls: Calls) -> None:
    result = invoke("open", "http://localhost:5173", "--mode", "proxy", "--frameless")

    assert result.exit_code == 0
    assert calls.last["window"] == Window(frameless=True)


def test_serve_can_proxy_an_address(calls: Calls) -> None:
    result = invoke("serve", "http://localhost:5173", "--mode", "proxy")

    assert result.exit_code == 0
    assert calls.last["source"] == Url("http://localhost:5173", mode="proxy")
    assert calls.last["window"] is None


def test_a_command_can_be_started_for_the_address(calls: Calls) -> None:
    invoke("open", "--run", "npm run dev", "--url", "http://localhost:5173")
    assert calls.last["source"] == Process("npm run dev", url="http://localhost:5173")

    invoke(
        "open",
        "http://localhost:5173",
        "--run",
        "npm run dev",
        "--run-cwd",
        "web",
        "--run-timeout",
        "90",
        "--mode",
        "proxy",
    )
    assert calls.last["source"] == Process(
        "npm run dev", url="http://localhost:5173", cwd=Path("web"), timeout=90, mode="proxy"
    )


def test_serve_can_start_a_command_too(calls: Calls) -> None:
    result = invoke("serve", "--run", "npm run dev", "--url", "http://x.test", "--mode", "proxy")

    assert result.exit_code == 0
    assert calls.last["source"] == Process("npm run dev", url="http://x.test", mode="proxy")
    assert calls.last["window"] is None


def test_the_dev_csp_profile_is_opt_in(calls: Calls) -> None:
    invoke("open", "web/dist")
    assert calls.last["security"].csp == Security().csp

    invoke("open", "web/dist", "--csp-profile", "dev")
    assert calls.last["security"].csp == DEV_CSP

    invoke("open", "web/dist", "--csp-profile", "strict")
    assert calls.last["security"].csp == Security().csp


def test_the_csp_profile_has_a_flag() -> None:
    assert "--csp-profile" in option_names("open")
    assert "--csp-profile" in option_names("serve")


def test_open_with_apps(calls: Calls) -> None:
    invoke("open", "--asgi", "proj.asgi:application", "--app-dir", "src")
    assert calls.last["source"] == Asgi("proj.asgi:application", app_dir=Path("src"))

    invoke("open", "--wsgi", "app:app")
    assert calls.last["source"] == Wsgi("app:app")


def test_open_with_web_dist_flag(calls: Calls) -> None:
    invoke("open", "--web-dist", "build")

    assert calls.last["source"] == Static(path=Path("build"))


# ----- serve ----------------------------------------------------------------------------------


def serve_and_announce(window: Any = None) -> Any:
    """A run() that starts a real headless shell and calls on_ready, like the real one."""

    def fake(source: Any = None, **kwargs: Any) -> None:
        with Shell(source, window=None) as shell:
            kwargs["on_ready"](shell)

    return fake


def test_serve_is_headless_and_announces_itself(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    monkeypatch.setattr("cornea.cli.commands.run_shell", serve_and_announce())

    result = invoke("serve", str(tmp_path))

    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    message = json.loads(lines[0])
    assert message["event"] == "ready"
    assert message["window"] is False
    assert message["url"].startswith(f"http://127.0.0.1:{message['port']}/?cornea_token=")
    assert "Serving http://127.0.0.1:" in result.stderr
    assert "Ctrl+C" in result.stderr


def test_serve_keeps_stderr_quiet_with_quiet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    monkeypatch.setattr("cornea.cli.commands.run_shell", serve_and_announce())

    result = invoke("--quiet", "serve", str(tmp_path))

    assert result.stderr == ""
    assert json.loads(result.stdout)["event"] == "ready"


def test_serve_passes_no_window(calls: Calls) -> None:
    invoke("serve", "web/dist", "--port", "9000")

    assert calls.last["window"] is None
    assert calls.last["server"] == Server(port=9000)
    assert callable(calls.last["on_ready"])


def test_serve_has_no_window_flags() -> None:
    result = invoke("serve", "web/dist", "--frameless")

    assert result.exit_code == 2


def test_serve_with_an_address_explains_that_it_needs_a_window() -> None:
    result = invoke("serve", "http://localhost:5173")

    assert result.exit_code == 1
    assert "needs a window" in result.stderr


# ----- mistakes are short messages, not tracebacks --------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["open", "web/dist", "--web-dist", "other"],
        ["open", "http://x.test", "--url", "http://y.test"],
        ["open", "--web-dist", "a", "--url", "http://x.test"],
        ["open", "--asgi", "a:b", "--wsgi", "c:d"],
        ["open", "--url", "http://x.test", "--no-spa"],
        ["open", "--asgi", "a:b", "--package", "p"],
        ["open", "--web-dist", "a", "--app-dir", "src"],
        ["open", "web/dist", "--size", "big"],
        ["open", "web/dist", "--size", "10x"],
        ["open", "web/dist", "--min-size", "1,2"],
        ["open", "web/dist", "--position", "10x20"],
        ["open", "web/dist", "--cookie-samesite", "none"],
        ["open", "web/dist", "--port", "high"],
        ["open", "web/dist", "--mode", "proxy"],
        ["open", "--asgi", "a:b", "--mode", "proxy"],
        ["open", "http://x.test", "--mode", "other"],
        ["open", "web/dist", "--csp", "default-src 'none'", "--csp-profile", "dev"],
        ["open", "web/dist", "--csp-profile", "loose"],
        ["open", "--run", "npm run dev"],
        ["open", "--run", "npm run dev", "--url", "http://x.test", "--web-dist", "web"],
        ["open", "--run", "npm run dev", "--asgi", "a:b", "--url", "http://x.test"],
        ["open", "http://x.test", "--run-cwd", "web"],
        ["open", "http://x.test", "--run-timeout", "5"],
        ["open", "--run", "npm run dev", "--url", "http://x.test", "--run-timeout", "soon"],
    ],
)
def test_bad_combinations_are_usage_errors(args: list[str], calls: Calls) -> None:
    result = invoke(*args)

    assert result.exit_code == 2
    assert calls.items == []
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["open", "web/dist", "--port", "99999"], "port"),
        (["open", "web/dist", "--api-prefix", "api"], "api_prefix"),
        (["open", "web/dist", "--size", "0x0"], "size"),
        (["open", "web/dist", "--token-ttl", "0"], "token_ttl"),
    ],
)
def test_invalid_setting_values_are_short_errors(
    args: list[str], message: str, calls: Calls
) -> None:
    result = invoke(*args)

    assert result.exit_code == 1
    assert message in result.stderr
    assert result.stderr.startswith("Error:")
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("web bundle not found"),
        RuntimeError("WebView2 is missing"),
        ImportError("cannot import module"),
        OSError("address in use"),
        ValueError("bad value"),
    ],
)
def test_failures_while_running_are_short_errors(
    error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise error

    monkeypatch.setattr("cornea.cli.commands.run_shell", fail)

    result = invoke("open", "web/dist")

    assert result.exit_code == 1
    # The details table comes first; the error is the last line and a single short message.
    assert result.stderr.strip().splitlines()[-1] == f"Error: {error}"
    assert result.stderr.count("Error:") == 1


def test_an_unknown_action_to_disable_is_a_short_error(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")

    result = invoke("serve", str(tmp_path), "--disable-action", "nothing")

    assert result.exit_code == 1
    assert "unknown built-in" in result.stderr


def test_a_missing_webview2_is_reported_before_anything_opens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    monkeypatch.setattr(window_module, "_registry_version", lambda: None)

    result = invoke("open", str(tmp_path))

    assert result.exit_code == 1
    assert "WebView2 runtime is not installed" in result.stderr


def test_a_missing_bundle_is_reported_by_serve(tmp_path: Path) -> None:
    result = invoke("serve", str(tmp_path / "missing"))

    assert result.exit_code == 1
    assert "folder not found" in result.stderr


# ----- the helpers ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "separator", "expected"),
    [("1200x800", "x", (1200, 800)), ("1200X800", "x", (1200, 800)), ("-5,10", ",", (-5, 10))],
)
def test_pairs_are_parsed(text: str, separator: str, expected: tuple[int, int]) -> None:
    assert options.parse_pair(text, "--size", separator) == expected


@pytest.mark.parametrize("text", ["", "1200", "axb", "1x2x3", "1.5x2"])
def test_bad_pairs_name_the_flag(text: str) -> None:
    with pytest.raises(typer.BadParameter, match="--size looks like 1200x800"):
        options.parse_pair(text, "--size", "x")


def test_position_errors_show_the_right_example() -> None:
    with pytest.raises(typer.BadParameter, match="100,50"):
        options.parse_pair("x", "--position", ",")


# ----- --measure --------------------------------------------------------------------------------


def test_measure_is_passed_on(calls: Calls) -> None:
    assert invoke("open", "web", "--measure").exit_code == 0

    assert callable(calls.last["measure"])


def test_measure_is_off_by_default_on_the_command_line(calls: Calls) -> None:
    invoke("open", "web")

    assert calls.last["measure"] is False


def test_the_json_options_need_measure(calls: Calls) -> None:
    result = invoke("serve", "web", "--json-friendly")

    assert result.exit_code == 2
    assert not calls.items


def test_measure_can_print_json_and_write_a_file(calls: Calls, tmp_path: Path) -> None:
    target = tmp_path / "out" / "timings.json"
    invoke("serve", "web", "--measure", "--json-friendly", "--json-file", str(target))

    report = calls.last["measure"]
    assert callable(report)
    report(Timings(server_ready=0.05))

    assert json.loads(target.read_text(encoding="utf-8"))["server_ready"] == 0.05


def test_measure_with_only_a_file_still_prints_the_line(
    calls: Calls, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invoke("open", "web", "--measure", "--json-file", str(tmp_path / "t.json"))
    calls.last["measure"](Timings(server_ready=0.05))

    err = capsys.readouterr().err
    assert "Start-up time" in err
    assert "server_ready" in err
    assert "0.050" in err


# ----- the details table ------------------------------------------------------------------------


def test_open_shows_what_it_will_do(calls: Calls) -> None:
    result = invoke("open", "web/dist", "--title", "Notes", "--frameless", "--app-id", "a.b")

    assert result.exit_code == 0
    assert "cornea open" in result.stderr
    assert "folder web" in result.stderr
    assert "'Notes', frameless" in result.stderr
    assert "a.b" in result.stderr


def test_serve_shows_its_source_and_never_a_window(calls: Calls) -> None:
    result = invoke("serve", "http://localhost:5173", "--mode", "proxy")

    assert "cornea serve" in result.stderr
    assert "http://localhost:5173 (proxy)" in result.stderr
    assert "Window" not in result.stderr


def test_quiet_hides_the_details(calls: Calls) -> None:
    result = invoke("--quiet", "open", "web/dist")

    assert result.stderr == ""


def test_a_started_command_is_described(calls: Calls) -> None:
    result = invoke("serve", "--run", "npm run dev", "--url", "http://localhost:5173")

    assert "started with: npm run dev" in result.stderr
