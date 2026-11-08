import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
import typer

from cli_support import Calls, invoke, option_names
from cornea import (
    App,
    Asgi,
    Bridge,
    Loading,
    Process,
    Security,
    Server,
    Static,
    Timings,
    Url,
    Window,
    Wsgi,
)
from cornea.cli import options
from cornea.core.window import window as window_module

pytestmark = pytest.mark.usefixtures("restore_cornea_logging")


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
        "drop_files": "--drop-files",
        "downloads": "--downloads",
        "icon": "--icon",
    },
    Bridge: {
        "disabled": "--disable-action",
        "open_files": "--open-files",
        "notifications": "--notifications",
    },
    Loading: {
        "subtitle": "--loading-subtitle",
        "title": "--loading-title",
        "icon": "--loading-icon",
        "theme": "--loading-theme",
        "background": "--loading-background",
        "foreground": "--loading-foreground",
        "html": "--loading-html",
        "min_display": "--loading-min-display",
    },
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


@pytest.mark.parametrize("settings", FLAGS, ids=lambda cls: cls.__name__)
def test_every_setting_has_a_flag(settings: type) -> None:
    fields = {field.name for field in dataclasses.fields(settings)}

    # A new setting fails here until it is given a flag and listed above.
    assert fields == set(FLAGS[settings])
    assert set(FLAGS[settings].values()) <= option_names("open")


def test_serve_has_every_flag_except_the_window_ones() -> None:
    window_flags = (
        set(FLAGS[Window].values())
        | set(FLAGS[Loading].values())
        | set(FLAGS[App].values())
        | {"--loading"}
    )

    assert option_names("serve") == option_names("open") - window_flags
    assert window_flags <= option_names("open")


def test_the_url_and_app_sources_have_flags() -> None:
    names = option_names("open")

    assert {"--url", "--asgi", "--wsgi", "--app-dir"} <= names
    assert {Url, Asgi, Wsgi}


# ----- open -----------------------------------------------------------------------------------


# ----- serve ----------------------------------------------------------------------------------


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


def test_quiet_hides_the_details(calls: Calls) -> None:
    result = invoke("--quiet", "open", "web/dist")

    assert result.stderr == ""


def test_a_started_command_is_described(calls: Calls) -> None:
    result = invoke("serve", "--run", "npm run dev", "--url", "http://localhost:5173")

    assert "started with: npm run dev" in result.stderr
