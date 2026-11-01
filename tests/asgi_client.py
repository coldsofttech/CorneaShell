import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote


@dataclass
class Response:
    """What an ASGI app sent back for one request."""

    status: int
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""

    def header(self, name: str) -> str | None:
        values = self.values(name)
        return values[0] if values else None

    def values(self, name: str) -> list[str]:
        return [value for key, value in self.headers if key == name.lower()]


@dataclass
class WebSocketResult:
    """How a WebSocket handshake ended."""

    closed_with: int | None
    reached_app: bool


class AsgiClient:
    """Sends single requests through an ASGI app without a server or a framework."""

    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    def request(
        self,
        path: str = "/",
        *,
        method: str = "GET",
        query: str = "",
        host: str | None = "127.0.0.1:8000",
        origin: str | None = None,
        cookie: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        raw_headers = [(b"host", host.encode())] if host is not None else []
        if origin is not None:
            raw_headers.append((b"origin", origin.encode()))
        if cookie is not None:
            raw_headers.append((b"cookie", cookie.encode()))
        for name, value in (headers or {}).items():
            raw_headers.append((name.lower().encode(), value.encode()))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            # Servers percent-decode the path before the app sees it.
            "path": unquote(path),
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": raw_headers,
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 8000),
        }
        sent: list[dict[str, Any]] = []

        requests = [{"type": "http.request", "body": b"", "more_body": False}]

        async def receive() -> dict[str, Any]:
            if requests:
                return requests.pop()
            # Like a real client: nothing more arrives, so waiters (file responses) stay parked
            # until the response finishes and they are cancelled.
            await asyncio.sleep(3600)
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        asyncio.run(self.app(scope, receive, send))
        start = next(m for m in sent if m["type"] == "http.response.start")
        return Response(
            status=start["status"],
            headers=[(k.decode().lower(), v.decode()) for k, v in start["headers"]],
            body=b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body"),
        )

    def websocket(
        self,
        path: str = "/ws",
        *,
        host: str | None = "127.0.0.1:8000",
        origin: str | None = "http://127.0.0.1:8000",
        cookie: str | None = None,
    ) -> WebSocketResult:
        headers = [(b"host", host.encode())] if host is not None else []
        if origin is not None:
            headers.append((b"origin", origin.encode()))
        if cookie is not None:
            headers.append((b"cookie", cookie.encode()))
        scope = {"type": "websocket", "path": path, "headers": headers, "query_string": b""}
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "websocket.connect"}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        asyncio.run(self.app(scope, receive, send))
        closes = [m["code"] for m in sent if m["type"] == "websocket.close"]
        accepted = any(m["type"] == "websocket.accept" for m in sent)
        return WebSocketResult(closed_with=closes[0] if closes else None, reached_app=accepted)
