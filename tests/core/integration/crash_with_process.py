"""Start a dev-server command, report its port, then die without cleaning up.

Run by test_process_crash.py. It is not a test file itself.
"""

import os
import sys
from pathlib import Path

from cornea import Process
from cornea.core.sources.process import ProcessRunner

DEVSERVER = Path(__file__).resolve().parents[2] / "devserver.py"


def main() -> None:
    port = int(sys.argv[1])
    command = (sys.executable, str(DEVSERVER), "--port", str(port))
    ProcessRunner(Process(command, url=f"http://127.0.0.1:{port}")).start()
    sys.stdout.write("ready\n")
    sys.stdout.flush()
    os._exit(1)  # no stop(), no atexit: like a crash


if __name__ == "__main__":
    main()
