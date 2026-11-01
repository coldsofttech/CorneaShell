"""The served JavaScript client, blocked-content reports, downloads, and ``cornea doctor``."""

import http.client
import json
import logging
import socket
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cornea import Security, Shell, Static, Window
from cornea.cli import app, doctor
from cornea.core.window.window import show_window
from window_fakes import FakeWebview

runner = CliRunner()


@pytest.fixture(autouse=True)
def local_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the log folder that doctor checks inside the test's own folder."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))


@pytest.fixture
def shell(tmp_path: Path) -> Any:
    (tmp_path / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    with Shell(Static(tmp_path), window=None) as running:
        yield running


def request(
    shell: Shell,
    path: str,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    data = response.read()
    result = (response.status, {k.lower(): v for k, v in response.getheaders()}, data)
    connection.close()
    return result


def signed_in(shell: Shell) -> dict[str, str]:
    _, headers, _ = request(shell, f"/?cornea_token={shell.app.state.bootstrap_token}")
    return {"Cookie": headers["set-cookie"].split(";")[0]}


# ----- the JavaScript client ----------------------------------------------------------------------


def test_the_client_script_is_served_with_the_prefix(shell: Shell) -> None:
    status, headers, body = request(shell, "/api/client.js", headers=signed_in(shell))

    assert status == 200
    assert headers["content-type"].startswith("text/javascript")
    text = body.decode()
    assert 'var PREFIX = "/api";' in text
    assert "__API_PREFIX__" not in text
    assert "window.cornea" in text


def test_the_client_script_needs_the_session(shell: Shell) -> None:
    assert request(shell, "/api/client.js")[0] == 401


def test_the_client_uses_a_custom_prefix(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    with Shell(Static(tmp_path), window=None, security=Security(api_prefix="/v1")) as custom:
        _, _, body = request(custom, "/v1/client.js", headers=signed_in(custom))

    assert 'var PREFIX = "/v1";' in body.decode()


def test_the_client_has_no_inline_code_to_block() -> None:
    from cornea.core.page.routes import _client_source

    source = _client_source()
    for name in (
        "minimize",
        "maximize",
        "restore",
        "close",
        "setTitle",
        "closeGuard",
        "call",
        "on",
    ):
        assert name in source


# ----- reports of blocked content ------------------------------------------------------------


def test_the_policy_names_where_to_report(shell: Shell) -> None:
    _, headers, _ = request(shell, "/", headers=signed_in(shell))

    assert headers["content-security-policy"].endswith("report-uri /api/csp-report")


def test_a_report_is_logged_without_the_query(
    shell: Shell, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="cornea")
    report = {
        "csp-report": {
            "effective-directive": "script-src-elem",
            "blocked-uri": "inline",
            "document-uri": "http://127.0.0.1:1/page?cornea_token=SECRET",
            "source-file": "http://127.0.0.1:1/app.js?x=1",
            "line-number": 12,
        }
    }

    status, _, _ = request(
        shell,
        "/api/csp-report",
        "POST",
        json.dumps(report).encode(),
        {"Content-Type": "application/csp-report"},
    )

    assert status == 204  # and no cookie or Origin was needed
    assert "script-src-elem" in caplog.text
    assert "blocked: ?" in caplog.text or "inline" in caplog.text
    assert "SECRET" not in caplog.text
    assert "x=1" not in caplog.text
    assert "app.js:12" in caplog.text


def test_a_big_or_broken_report_is_ignored(shell: Shell, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="cornea")

    big = request(shell, "/api/csp-report", "POST", b"x" * 20000)
    broken = request(shell, "/api/csp-report", "POST", b"not json")

    assert big[0] == broken[0] == 204
    assert "Blocked by the content security policy" not in caplog.text


def test_other_posts_still_need_an_origin(shell: Shell) -> None:
    assert request(shell, "/api/bridge/platform_info", "POST", b"{}", signed_in(shell))[0] == 403


# ----- downloads -----------------------------------------------------------------------------


@pytest.mark.parametrize("allowed", [False, True])
def test_downloads_follow_the_setting(allowed: bool) -> None:
    webview = FakeWebview()

    show_window(webview, Window(downloads=allowed))

    assert webview.settings["ALLOW_DOWNLOADS"] is allowed


# ----- doctor --------------------------------------------------------------------------------


def test_the_checks_cover_each_thing_that_can_go_wrong(tmp_path: Path) -> None:
    names = {check.name for check in doctor.run_checks(start=tmp_path)}

    assert {"Python", "Platform", "Optional extras", "Settings file", "Log folder"} <= names
    assert "Loopback port" in names


def test_a_valid_settings_file_passes(tmp_path: Path) -> None:
    (tmp_path / "cornea.toml").write_text("[window]\ntitle = 'x'\n", encoding="utf-8")

    check = doctor._settings_file(tmp_path)

    assert check.status == "ok"
    assert "is valid" in check.detail


def test_a_bad_settings_file_is_a_problem(tmp_path: Path) -> None:
    (tmp_path / "cornea.toml").write_text("[window]\ncolour = 'red'\n", encoding="utf-8")

    check = doctor._settings_file(tmp_path)

    assert check.status == "fail"
    assert "unknown key" in check.detail


def test_a_busy_port_is_a_problem() -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]

        check = doctor._port(port)

    assert check.status == "fail"
    assert str(port) in check.detail


def test_a_free_port_passes() -> None:
    assert doctor._port(0).status == "ok"


def test_an_unwritable_log_folder_is_only_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(blocker))

    assert doctor._log_folder().status == "warn"


def test_the_log_folder_check_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert doctor._log_folder().status == "ok"
    assert list((tmp_path / "Cornea" / "logs").iterdir()) == []


def test_the_command_reports_and_exits_zero_when_all_is_well(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ok = doctor.Check("Python", "ok", "3.11")
    monkeypatch.setattr("cornea.cli.commands.run_checks", lambda port: [ok])

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Python" in result.stdout


def test_the_command_exits_one_on_a_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = doctor.Check("WebView2 runtime", "fail", "not installed")
    monkeypatch.setattr("cornea.cli.commands.run_checks", lambda port: [bad])

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "not installed" in result.stdout


def test_the_command_can_print_json(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = doctor.Check("Python", "ok", "3.11")
    monkeypatch.setattr("cornea.cli.commands.run_checks", lambda port: [ok])

    result = runner.invoke(app, ["doctor", "--json"])

    assert json.loads(result.stdout) == [{"name": "Python", "status": "ok", "detail": "3.11"}]


def test_the_command_passes_the_port_on(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    def fake_checks(port: int) -> list[doctor.Check]:
        seen.append(port)
        return []

    monkeypatch.setattr("cornea.cli.commands.run_checks", fake_checks)

    runner.invoke(app, ["doctor", "--port", "8765"])

    assert seen == [8765]
