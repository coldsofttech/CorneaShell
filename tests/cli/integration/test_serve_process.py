import http.client
import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>served</html>", encoding="utf-8")
    return tmp_path


def test_serve_prints_one_ready_line_and_serves(bundle: Path) -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "cornea.cli", "--quiet", "serve", str(bundle)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        message = json.loads(process.stdout.readline())

        connection = http.client.HTTPConnection("127.0.0.1", message["port"], timeout=5)
        connection.request("GET", "/health")
        health = connection.getresponse()
        assert health.status == 200
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", message["port"], timeout=5)
        connection.request("GET", message["url"].split(str(message["port"]), 1)[1])
        signed_in = connection.getresponse()
        cookie = (signed_in.getheader("Set-Cookie") or "").split(";")[0]
        assert signed_in.status == 303
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", message["port"], timeout=5)
        connection.request("GET", "/", headers={"Cookie": cookie})
        page = connection.getresponse()
        assert page.read() == b"<html>served</html>"
        connection.close()
    finally:
        process.terminate()
        process.wait(timeout=10)

    assert message["event"] == "ready"
    assert message["window"] is False
