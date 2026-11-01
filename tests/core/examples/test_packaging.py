"""A Cornea app frozen with PyInstaller still starts and serves its page.

This builds a real executable, which takes a minute or two, so it only runs with
``pytest -m toolchains`` and when PyInstaller is installed (``uv sync --group packaging``).
Only the headless start is checked: showing the window needs a person at a screen.
"""

import http.client
import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.toolchains

APP = """
import sys
from pathlib import Path

from cornea import Shell, Static, ready_line

# Frozen, the files added with --add-data are unpacked next to the executable (sys._MEIPASS).
base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
shell = Shell(Static(base / "web"), window=None)
shell.run(on_ready=lambda ready: print(ready_line(ready), flush=True))
"""
BUILD_SECONDS = 600
START_SECONDS = 60


@pytest.fixture
def frozen(tmp_path: Path) -> Path:
    if importlib.util.find_spec("PyInstaller") is None:
        pytest.skip("PyInstaller is not installed (uv sync --group packaging)")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<h1>Frozen Cornea</h1>", encoding="utf-8")
    (tmp_path / "app.py").write_text(APP, encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onedir",
            "--name",
            "demo",
            "--collect-submodules",
            "uvicorn",
            "--collect-data",
            "cornea",
            "--add-data",
            f"{tmp_path / 'web'};web",
            "--distpath",
            str(tmp_path / "dist"),
            "--workpath",
            str(tmp_path / "build"),
            "--specpath",
            str(tmp_path),
            str(tmp_path / "app.py"),
        ],
        check=True,
        timeout=BUILD_SECONDS,
        capture_output=True,
    )
    return tmp_path / "dist" / "demo" / "demo.exe"


def test_the_frozen_app_serves_its_page_and_the_client_script(frozen: Path) -> None:
    try:
        process = subprocess.Popen([str(frozen)], stdout=subprocess.PIPE, text=True)
    except OSError as exc:
        # Smart App Control or a company policy can refuse to run a program nobody has signed.
        pytest.skip(f"this machine will not run the unsigned executable that was built: {exc}")
    watchdog = threading.Timer(START_SECONDS, process.kill)
    watchdog.start()
    try:
        assert process.stdout is not None
        ready = json.loads(process.stdout.readline())
        token = ready["url"].split("cornea_token=")[1]

        def get(path: str, cookie: str = "") -> tuple[int, str, str]:
            connection = http.client.HTTPConnection("127.0.0.1", ready["port"], timeout=10)
            connection.request("GET", path, headers={"Cookie": cookie} if cookie else {})
            response = connection.getresponse()
            result = (
                response.status,
                response.getheader("Set-Cookie") or "",
                response.read().decode(),
            )
            connection.close()
            return result

        cookie = get(f"/?cornea_token={token}")[1].split(";")[0]
        assert "Frozen Cornea" in get("/", cookie)[2]
        # The data file that ships inside the package must have been bundled too.
        assert "window.cornea" in get("/api/client.js", cookie)[2]
    finally:
        watchdog.cancel()
        process.kill()
        process.wait(timeout=30)
