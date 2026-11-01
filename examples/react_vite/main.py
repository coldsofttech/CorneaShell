"""A React project built with Vite.

Build first with: npm install && npm run build (in this folder).
Built files:               python examples/react_vite/main.py
Dev server, hot reload:    python examples/react_vite/main.py --dev
Add --headless for a browser tab instead of a window.
"""

import argparse
import sys
from pathlib import Path

from cornea import DEV_CSP, Process, Security, Shell, Static, Window, ready_line

HERE = Path(__file__).parent
DEV_URL = "http://127.0.0.1:5173"


def build_shell(*, headless: bool = False, dev: bool = False, frameless: bool = True) -> Shell:
    window = None if headless else Window(title="React + Vite", frameless=frameless)
    if dev:
        # Cornea starts Vite, serves it through its own address and stops it with the window.
        # Vite injects inline scripts and styles, so the development policy is needed.
        source = Process(
            "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
            url=DEV_URL,
            cwd=HERE,
            mode="proxy",
        )
        return Shell(source, security=Security(csp=DEV_CSP), window=window)
    dist = HERE / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("There is no build yet. Run: npm install && npm run build")
    return Shell(Static(dist), window=window)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dev", action="store_true", help="run the Vite dev server")
    parser.add_argument("--headless", action="store_true", help="no window; print the address")
    parser.add_argument("--native-frame", action="store_true", help="use the normal window frame")
    args = parser.parse_args()
    shell = build_shell(headless=args.headless, dev=args.dev, frameless=not args.native_frame)
    if args.headless:
        shell.run(on_ready=lambda ready: sys.stdout.write(ready_line(ready) + "\n"))
    else:
        shell.run()


if __name__ == "__main__":
    main()
