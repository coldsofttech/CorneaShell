"""A MkDocs documentation site shown in Cornea like an offline help viewer.

Built site:                python examples/mkdocs_site/main.py
Live, reloads on edits:    python examples/mkdocs_site/main.py --live
Add --headless for a browser tab. Needs the examples group: uv sync --group examples
"""

import argparse
import subprocess
import sys
from pathlib import Path

from cornea import DEV_CSP, Process, Security, Shell, Static, Window, ready_line

HERE = Path(__file__).parent


def build_shell(*, headless: bool = False, live: bool = False, port: int = 8000) -> Shell:
    window = None if headless else Window(title="MkDocs example")
    if live:
        # mkdocs serve reloads the page over a WebSocket and injects inline scripts.
        command = (sys.executable, "-m", "mkdocs", "serve", "-a", f"127.0.0.1:{port}")
        source = Process(command, url=f"http://127.0.0.1:{port}", cwd=HERE, mode="proxy")
        return Shell(source, security=Security(csp=DEV_CSP), window=window)
    subprocess.run([sys.executable, "-m", "mkdocs", "build", "--quiet"], cwd=HERE, check=True)
    return Shell(Static(HERE / "site"), window=window)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="run mkdocs serve")
    parser.add_argument("--headless", action="store_true", help="no window; print the address")
    parser.add_argument("--port", type=int, default=8000, help="with --live")
    args = parser.parse_args()
    shell = build_shell(headless=args.headless, live=args.live, port=args.port)
    if args.headless:
        shell.run(on_ready=lambda ready: sys.stdout.write(ready_line(ready) + "\n"))
    else:
        shell.run()


if __name__ == "__main__":
    main()
