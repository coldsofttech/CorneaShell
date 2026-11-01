"""A reverse proxy for another server's pages.

The page is fetched through Cornea, so it comes from Cornea's address and gets Cornea's security,
headers and window controls. The address to forward to is fixed by configuration and never taken
from a request.
"""

import asyncio
import contextlib
import logging
import re
from collections.abc import AsyncIterator, Iterable
from typing import Any
from urllib.parse import urlsplit

from cornea.core.asgi import Receive, Scope, Send
from cornea.core.security.security import SESSION_COOKIE_PATTERN

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5.0
HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
# Cornea's own server adds these to every response, so the upstream's would appear twice.
REGENERATED = frozenset({"date", "server"})
_DOMAIN = re.compile(r";\s*domain=[^;]*", re.IGNORECASE)
_NO_BODY_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE", "TRACE"})
_BAD_GATEWAY = (
    "<!doctype html><title>Cannot reach the page</title>"
    "<h1>Cannot reach the page</h1><p>Cornea could not connect to <code>{origin}</code>. "
    "Is that server running?</p>"
)


def without_session_cookie(cookie_header: str) -> str | None:
    """The ``Cookie`` header without Cornea's own session cookie, or ``None`` if nothing is left."""
    kept = [
        part.strip()
        for part in cookie_header.split(";")
        if part.strip() and not SESSION_COOKIE_PATTERN.match(part.partition("=")[0].strip())
    ]
    return "; ".join(kept) or None


class ProxyApp:
    """An ASGI app that forwards HTTP and WebSocket traffic to ``upstream``.

    Example:
        >>> ProxyApp("http://localhost:5173/").origin
        'http://localhost:5173'
    """

    def __init__(self, upstream: str) -> None:
        try:
            import httpx
            import websockets  # noqa: F401 - only checking that it is installed
        except ImportError as exc:
            raise ImportError(
                "Proxy mode needs the 'proxy' extra: pip install \"cornea-shell[proxy]\""
            ) from exc
        parts = urlsplit(upstream)
        self.origin = f"{parts.scheme}://{parts.netloc}"
        self.base_path = parts.path.rstrip("/")
        self._ws_origin = ("wss" if parts.scheme == "https" else "ws") + f"://{parts.netloc}"
        # trust_env=False: a proxy configured in the environment must not catch local traffic.
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(CONNECT_TIMEOUT, read=None, write=30.0, pool=CONNECT_TIMEOUT),
            follow_redirects=False,
            trust_env=False,
        )

    async def aclose(self) -> None:
        """Release the connections to the upstream server."""
        await self._client.aclose()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            await self._http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._websocket(scope, receive, send)

    # ----- helpers ----------------------------------------------------------------------------

    def _target(self, scope: Scope) -> str:
        path = (scope.get("raw_path") or scope["path"].encode()).decode("latin-1")
        query = scope.get("query_string", b"").decode("latin-1")
        return f"{self.origin}{self.base_path}{path}" + (f"?{query}" if query else "")

    def _request_headers(self, scope: Scope) -> list[tuple[str, str]]:
        """The request's headers, adjusted so the upstream sees itself as the origin."""
        headers: list[tuple[str, str]] = []
        for raw_name, raw_value in scope["headers"]:
            name, value = raw_name.decode("latin-1"), raw_value.decode("latin-1")
            lowered = name.lower()
            if lowered in HOP_BY_HOP or lowered == "host":
                continue
            if lowered == "cookie":
                kept = without_session_cookie(value)
                if kept is not None:
                    headers.append((name, kept))
            elif lowered == "origin":
                headers.append((name, self.origin))
            elif lowered == "referer":
                parts = urlsplit(value)
                path = parts.path + (f"?{parts.query}" if parts.query else "")
                headers.append((name, f"{self.origin}{path}"))
            else:
                headers.append((name, value))
        return headers

    def _response_headers(self, headers: Iterable[tuple[str, str]]) -> list[tuple[bytes, bytes]]:
        out: list[tuple[bytes, bytes]] = []
        for name, value in headers:
            lowered = name.lower()
            if lowered in HOP_BY_HOP or lowered in REGENERATED:
                continue
            if lowered == "location" and value.startswith(self.origin):
                value = value.removeprefix(self.origin) or "/"
            elif lowered == "set-cookie":
                value = _DOMAIN.sub("", value)
            out.append((lowered.encode("latin-1"), value.encode("latin-1")))
        return out

    # ----- HTTP -------------------------------------------------------------------------------

    async def _http(self, scope: Scope, receive: Receive, send: Send) -> None:
        import httpx

        headers = self._request_headers(scope)
        has_body = scope["method"] not in _NO_BODY_METHODS or any(
            name.lower() in {"content-length", "transfer-encoding"} and value != "0"
            for name, value in headers
        )

        async def body() -> AsyncIterator[bytes]:
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    return
                if chunk := message.get("body", b""):
                    yield chunk
                if not message.get("more_body", False):
                    return

        request = self._client.build_request(
            scope["method"],
            self._target(scope),
            headers=headers,
            content=body() if has_body else None,
        )
        try:
            response = await self._client.send(request, stream=True)
        except httpx.HTTPError as exc:
            logger.debug("Could not reach %s for %s: %s", self.origin, scope["path"], exc)
            await self._bad_gateway(send)
            return
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": response.status_code,
                    "headers": self._response_headers(response.headers.multi_items()),
                }
            )
            # Raw bytes: the body stays compressed, as the client asked, and nothing is buffered.
            async for chunk in response.aiter_raw():
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            await response.aclose()

    async def _bad_gateway(self, send: Send) -> None:
        page = _BAD_GATEWAY.format(origin=self.origin).encode()
        headers = [
            (b"content-type", b"text/html; charset=utf-8"),
            (b"content-length", str(len(page)).encode()),
        ]
        await send({"type": "http.response.start", "status": 502, "headers": headers})
        await send({"type": "http.response.body", "body": page})

    # ----- WebSocket --------------------------------------------------------------------------

    async def _websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        from websockets.asyncio.client import connect
        from websockets.typing import Origin

        await receive()  # websocket.connect
        headers = [
            (name, value)
            for name, value in self._request_headers(scope)
            if name.lower() in {"cookie", "authorization", "user-agent", "accept-language"}
        ]
        path = (scope.get("raw_path") or scope["path"].encode()).decode("latin-1")
        query = scope.get("query_string", b"").decode("latin-1")
        uri = f"{self._ws_origin}{self.base_path}{path}" + (f"?{query}" if query else "")
        try:
            upstream = await connect(
                uri,
                origin=Origin(self.origin),
                subprotocols=scope.get("subprotocols") or None,
                additional_headers=headers,
                open_timeout=CONNECT_TIMEOUT,
                max_size=2**24,
                proxy=None,
            )
        except Exception as exc:
            logger.debug("Could not open a WebSocket to %s%s: %s", self.origin, scope["path"], exc)
            await send({"type": "websocket.close", "code": 1014})
            return
        await send({"type": "websocket.accept", "subprotocol": upstream.subprotocol})
        await _pump(upstream, receive, send)


async def _pump(upstream: Any, receive: Receive, send: Send) -> None:
    """Copy messages both ways until either side closes, then close the other."""

    async def to_upstream() -> None:
        while True:
            message = await receive()
            if message["type"] != "websocket.receive":
                return
            data = message.get("text")
            await upstream.send(data if data is not None else message.get("bytes", b""))

    async def to_client() -> None:
        async for data in upstream:
            if isinstance(data, str):
                await send({"type": "websocket.send", "text": data})
            else:
                await send({"type": "websocket.send", "bytes": data})

    tasks = [asyncio.ensure_future(to_upstream()), asyncio.ensure_future(to_client())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await upstream.close()
    code = upstream.close_code
    if code is None or code in {1005, 1006, 1015}:  # these may not be sent in a close frame
        code = 1000
    with contextlib.suppress(Exception):  # the client may already have gone
        await send({"type": "websocket.close", "code": code})
