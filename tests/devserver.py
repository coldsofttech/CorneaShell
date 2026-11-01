"""A stand-in dev server for tests. It is run as a command, never imported.

python devserver.py --port 5000                       serve a page
python devserver.py --port 5000 --child-port-file f   also start a child server (a tree)
python devserver.py --exit-code 3                     print something and fail
python devserver.py --never-listen                    start up but never listen
"""

import argparse
import http.server
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"dev server page"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--never-listen", action="store_true")
    parser.add_argument("--child-port-file")
    parser.add_argument("--noisy", action="store_true")
    parser.add_argument("--print-cwd", action="store_true")
    args = parser.parse_args()

    if args.print_cwd:
        sys.stdout.write(f"cwd={os.getcwd()}\n")
        sys.stdout.flush()
    if args.noisy:
        for number in range(200):
            sys.stdout.write(f"line {number}\n")
        sys.stdout.flush()
    if args.exit_code is not None:
        sys.stdout.write("failing on purpose\n")
        sys.stdout.flush()
        sys.exit(args.exit_code)
    if args.never_listen:
        sys.stdout.write("starting up...\n")
        sys.stdout.flush()
        time.sleep(60)
        return
    if args.child_port_file:
        child_port = free_port()
        subprocess.Popen([sys.executable, __file__, "--port", str(child_port)])
        Path(args.child_port_file).write_text(str(child_port), encoding="utf-8")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
