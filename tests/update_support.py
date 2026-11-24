"""A tiny local web server that serves files and JSON for the update tests."""

import hashlib
import json


class Site:
    """Routes to bytes. ``base`` is the loopback address the server answers on."""

    def __init__(self) -> None:
        self.routes: dict[str, bytes] = {}
        self.base = ""
        self.hits: list[str] = []

    def add(self, path: str, body: bytes | dict[str, object] | list[object]) -> str:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.routes[path] = data
        return self.base + path

    @staticmethod
    def sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
