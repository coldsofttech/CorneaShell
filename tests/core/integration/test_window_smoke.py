import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from cornea.core.window import window as window_module

pytestmark = pytest.mark.skipif(
    sys.platform != "win32"
    or importlib.util.find_spec("webview") is None
    or window_module._registry_version() is None,
    reason="needs Windows with pywebview and the WebView2 runtime",
)


def test_a_real_window_loads_the_page_and_follows_the_settings() -> None:
    probe = Path(__file__).with_name("window_probe.py")

    result = subprocess.run(
        [sys.executable, str(probe)], capture_output=True, text=True, timeout=90, check=False
    )

    lines = [line for line in result.stdout.splitlines() if line.startswith("REPORT ")]
    assert lines, result.stdout + result.stderr
    report = json.loads(lines[-1].removeprefix("REPORT "))
    assert "error" not in report, report
    # The page loaded through the one-time sign-in, so the window and the server work together.
    assert report["page_text"] == "Hello from Cornea"
    assert report["document_title"] == "Smoke page"
    # devtools=True turns the tools on without turning the context menu on.
    assert report["devtools"] is True
    assert report["context_menu"] is False
    # The window controls reach the real window, and closing it stops the server.
    assert report["maximized"] is True
    assert report["restored"] is True
    assert report["server_stopped"] is True
    assert result.returncode == 0
