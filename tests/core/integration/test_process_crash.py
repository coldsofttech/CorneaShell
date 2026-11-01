import socket
import subprocess
import sys
import time
from pathlib import Path


def port_is_free(port: int) -> bool:
    try:
        socket.create_server(("127.0.0.1", port)).close()
    except OSError:
        return False
    return True


def test_the_dev_server_dies_with_cornea_even_after_a_crash() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    script = Path(__file__).with_name("crash_with_process.py")

    result = subprocess.run(
        [sys.executable, str(script), str(port)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert "ready" in result.stdout, result.stderr
    assert result.returncode == 1
    deadline = time.monotonic() + 10
    while not port_is_free(port) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert port_is_free(port)
