"""A Streamlit app shown in Cornea. Cornea starts Streamlit and stops it with the window.

Run it in a window:        python examples/streamlit_app/main.py
Or in a browser tab:       python examples/streamlit_app/main.py --headless
Needs the examples group:  uv sync --group examples
"""

import argparse
import sys
from pathlib import Path

from cornea import DEV_CSP, Process, Security, Shell, Window, ready_line

HERE = Path(__file__).parent


def build_shell(*, headless: bool = False, frameless: bool = False, port: int = 8501) -> Shell:
    window = None if headless else Window(title="Streamlit example", frameless=frameless)
    command = (
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.headless",
        "true",
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
    )
    # Streamlit talks over a WebSocket, which the proxy forwards. It also injects inline scripts
    # and styles, so it needs the development policy: fine for a dev tool, not for a shipped app.
    source = Process(command, url=f"http://127.0.0.1:{port}", cwd=HERE, mode="proxy")
    return Shell(source, security=Security(csp=DEV_CSP), window=window)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headless", action="store_true", help="no window; print the address")
    parser.add_argument("--frameless", action="store_true", help="a window without a frame")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    shell = build_shell(headless=args.headless, frameless=args.frameless, port=args.port)
    if args.headless:
        shell.run(on_ready=lambda ready: sys.stdout.write(ready_line(ready) + "\n"))
    else:
        shell.run()


if __name__ == "__main__":
    main()
