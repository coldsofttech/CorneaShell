"""Go (net/http) shown in Cornea. Cornea starts the server and stops it with the window.

NOT RUN ON THE AUTHOR'S MACHINE (go is not installed there); tested by the examples workflow.

Needs Go 1.21 or newer.
Run it in a window:        python examples/go_server/main.py
Without the proxy:         python examples/go_server/main.py --mode direct
Or in a browser tab:       python examples/go_server/main.py --headless
"""

import argparse
import sys
from pathlib import Path
from typing import Literal

from cornea import Process, Shell, Window, ready_line

HERE = Path(__file__).parent


def command(port: int) -> tuple[str, ...]:
    """The command Cornea runs; the port is in it because Process takes no environment."""
    return ("go", "run", ".", str(port))


def build_shell(
    *,
    headless: bool = False,
    mode: Literal["direct", "proxy"] = "proxy",
    frameless: bool = False,
    port: int = 5104,
) -> Shell:
    if headless and mode == "direct":
        raise SystemExit("--headless needs --mode proxy: a direct address is shown by the window")
    window = None if headless else Window(title="Go (net/http)", frameless=frameless)
    # The first run may restore packages or compile, so allow plenty of time.
    source = Process(
        command(port), url=f"http://127.0.0.1:{port}", cwd=HERE, mode=mode, timeout=120
    )
    return Shell(source, window=window)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headless", action="store_true", help="no window; print the address")
    parser.add_argument("--mode", choices=("direct", "proxy"), default="proxy")
    parser.add_argument("--frameless", action="store_true", help="needs --mode proxy")
    parser.add_argument("--port", type=int, default=5104)
    args = parser.parse_args()
    shell = build_shell(
        headless=args.headless, mode=args.mode, frameless=args.frameless, port=args.port
    )
    if args.headless:
        shell.run(on_ready=lambda ready: sys.stdout.write(ready_line(ready) + "\n"))
    else:
        shell.run()


if __name__ == "__main__":
    main()
