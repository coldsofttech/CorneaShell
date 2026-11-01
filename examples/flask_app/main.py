"""A Flask app (WSGI) mounted in Cornea.

Run it in a window:        python examples/flask_app/main.py
Or in a browser tab:       python examples/flask_app/main.py --headless
"""

import argparse
import sys
from pathlib import Path

from cornea import Shell, Window, Wsgi, ready_line

HERE = Path(__file__).parent


def build_shell(*, headless: bool = False, frameless: bool = False) -> Shell:
    window = None if headless else Window(title="Flask example", frameless=frameless)
    return Shell(Wsgi("flask_example:app", app_dir=HERE), window=window)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headless", action="store_true", help="no window; print the address")
    parser.add_argument("--frameless", action="store_true", help="draw your own title bar")
    args = parser.parse_args()
    shell = build_shell(headless=args.headless, frameless=args.frameless)
    if args.headless:
        shell.run(on_ready=lambda ready: sys.stdout.write(ready_line(ready) + "\n"))
    else:
        shell.run()


if __name__ == "__main__":
    main()
