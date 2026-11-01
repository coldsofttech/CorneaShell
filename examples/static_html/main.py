"""Plain HTML, CSS and JavaScript with its own title bar.

Run it in a window:        python examples/static_html/main.py
Or in a browser tab:       python examples/static_html/main.py --headless
"""

import argparse
import sys
from pathlib import Path

from cornea import App, Shell, Static, Window, ready_line

HERE = Path(__file__).parent


def build_shell(*, headless: bool = False, frameless: bool = True, remember: bool = False) -> Shell:
    window = None if headless else Window(title="Plain HTML", frameless=frameless, icon="icon.png")
    app = App(id="com.example.static-html", remember_window=True) if remember else None
    return Shell(Static(HERE), window=window, identity=app)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headless", action="store_true", help="no window; print the address")
    parser.add_argument("--native-frame", action="store_true", help="use the normal window frame")
    parser.add_argument("--remember", action="store_true", help="remember the window's place")
    args = parser.parse_args()
    shell = build_shell(
        headless=args.headless, frameless=not args.native_frame, remember=args.remember
    )
    if args.headless:
        shell.run(on_ready=lambda ready: sys.stdout.write(ready_line(ready) + "\n"))
    else:
        shell.run()


if __name__ == "__main__":
    main()
