"""A tiny local web server that serves files and JSON for the update tests."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from update_support import Site


@pytest.fixture
def site() -> Iterator[Site]:
    state = Site()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            state.hits.append(self.path)
            path = self.path.split("?")[0]
            if path == "/redirect-insecure":
                self.send_response(302)
                self.send_header("Location", "http://example.invalid/app.zip")
                self.end_headers()
                return
            body = state.routes.get(path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.base = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
