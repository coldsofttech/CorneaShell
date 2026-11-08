import json
from pathlib import Path
from typing import Any

import pytest

from cli_support import Calls, invoke
from cornea import (
    Process,
    Server,
    Shell,
    Url,
)

pytestmark = pytest.mark.usefixtures("restore_cornea_logging")


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


def test_serve_can_proxy_an_address(calls: Calls) -> None:
    result = invoke("serve", "http://localhost:5173", "--mode", "proxy")

    assert result.exit_code == 0
    assert calls.last["source"] == Url("http://localhost:5173", mode="proxy")
    assert calls.last["window"] is None


def test_serve_can_start_a_command_too(calls: Calls) -> None:
    result = invoke("serve", "--run", "npm run dev", "--url", "http://x.test", "--mode", "proxy")

    assert result.exit_code == 0
    assert calls.last["source"] == Process("npm run dev", url="http://x.test", mode="proxy")
    assert calls.last["window"] is None


def test_serve_shows_its_source_and_never_a_window(calls: Calls) -> None:
    result = invoke("serve", "http://localhost:5173", "--mode", "proxy")

    assert "cornea serve" in result.stderr
    assert "http://localhost:5173 (proxy)" in result.stderr
    assert "Window" not in result.stderr
