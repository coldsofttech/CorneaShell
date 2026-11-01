"""Open a real Cornea window on a tiny bundle and print what happened as one JSON line.

Run by test_window_smoke.py in its own process, because pywebview owns the main thread and only
starts once per process. It is not a test file itself.
"""

import importlib
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from cornea import Shell, Static, Window
from cornea.core.window.window import _invoke

report: dict[str, Any] = {}


def probe(shell: Shell) -> None:
    webview = importlib.import_module("webview")
    try:
        deadline = time.time() + 30
        while time.time() < deadline and not (webview.windows and shell.app.state.window):
            time.sleep(0.1)
        window = webview.windows[0]
        window.events.loaded.wait(30)
        time.sleep(1.5)  # let the loaded handler narrow the WebView2 settings
        report["page_text"] = window.evaluate_js("document.body.innerText")
        report["document_title"] = window.evaluate_js("document.title")

        def read_settings() -> None:
            options = window.native.webview.CoreWebView2.Settings
            report["context_menu"] = options.AreDefaultContextMenusEnabled
            report["devtools"] = options.AreDevToolsEnabled

        _invoke(window.native, read_settings)
        controller = shell.app.state.window
        controller.maximize()
        time.sleep(1.2)
        report["maximized"] = controller.state()["maximized"]
        controller.restore()
        time.sleep(0.8)
        report["restored"] = not controller.state()["maximized"]
    except BaseException as exc:
        report["error"] = repr(exc)
    finally:
        shell.app.state.window.close()


def main() -> None:
    bundle = Path(tempfile.mkdtemp())
    (bundle / "index.html").write_text(
        "<html><head><title>Smoke page</title></head><body>Hello from Cornea</body></html>",
        encoding="utf-8",
    )
    shell = Shell(Static(bundle), window=Window(title="Cornea smoke test", devtools=True))
    threading.Thread(target=probe, args=(shell,), daemon=True).start()
    shell.run()
    report["server_stopped"] = not shell.running
    sys.stdout.write("REPORT " + json.dumps(report) + "\n")


if __name__ == "__main__":
    main()
