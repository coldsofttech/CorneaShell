"""A Node.js server shown in Cornea, started for you or already running.

Cornea starts server.js:   python examples/node_server/main.py
A server you started:      python examples/node_server/main.py --external
Add --mode proxy to serve it through Cornea (frameless possible), --headless for a browser tab.
"""

import argparse
import sys
from pathlib import Path
from typing import Literal

from cornea import Process, Shell, Url, Window, ready_line

HERE = Path(__file__).parent


def build_shell(
    *,
    headless: bool = False,
    mode: Literal["direct", "proxy"] = "direct",
    external: bool = False,
    frameless: bool = False,
    port: int = 3000,
) -> Shell:
    url = f"http://127.0.0.1:{port}"
    if headless and mode == "direct":
        raise SystemExit("--headless needs --mode proxy: a direct address is shown by the window")
    # A direct address is not served by Cornea, so the window keeps its normal frame.
    window = None if headless else Window(title="Node.js example", frameless=frameless)
    if external:
        return Shell(Url(url, mode=mode), window=window)
    # server.js takes the port as an argument, so the command carries it.
    command = ("node", "server.js", str(port))
    return Shell(Process(command, url=url, cwd=HERE, mode=mode), window=window)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headless", action="store_true", help="no window; print the address")
    parser.add_argument("--external", action="store_true", help="use a server you started")
    parser.add_argument("--mode", choices=("direct", "proxy"), default="direct")
    parser.add_argument("--frameless", action="store_true", help="needs --mode proxy")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()
    shell = build_shell(
        headless=args.headless,
        mode=args.mode,
        external=args.external,
        frameless=args.frameless,
        port=args.port,
    )
    if args.headless:
        shell.run(on_ready=lambda ready: sys.stdout.write(ready_line(ready) + "\n"))
    else:
        shell.run()


if __name__ == "__main__":
    main()
