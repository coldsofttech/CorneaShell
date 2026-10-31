import asyncio
import gzip
import http.client
import json
import socket
import sys
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from cornea import Security, Shell, Url, Window
from cornea.core.proxy import HOP_BY_HOP, ProxyApp, without_session_cookie

# ----- a real upstream server to proxy ----------------------------------------------------------


async def page(request: Request) -> Response:
    return Response("<html>upstream page</html>", media_type="text/html")


async def health(request: Request) -> Response:
    return PlainTextResponse("upstream health")


async def echo(request: Request) -> Response:
    body = await request.body()
    return JSONResponse(
        {
            "method": request.method,
            "path": request.scope["raw_path"].decode(),
            "query": request.scope["query_string"].decode(),
            "headers": dict(request.headers.items()),
            "body_length": len(body),
            "body_start": body[:20].decode("latin-1"),
        }
    )


async def redirect(request: Request) -> Response:
    host = request.headers["host"]
    return RedirectResponse(f"http://{host}/target?x=1", status_code=302)


async def cookies(request: Request) -> Response:
    response = Response("ok")
    response.headers.append("set-cookie", "a=1; Domain=127.0.0.1; Path=/")
    response.headers.append("set-cookie", "b=2; Path=/; HttpOnly")
    return response


async def stream(request: Request) -> Response:
    async def chunks() -> Any:
        for index in range(4):
            yield f"chunk{index};".encode()
            await asyncio.sleep(0.05)

    return StreamingResponse(chunks(), media_type="text/plain")


async def compressed(request: Request) -> Response:
    return Response(
        gzip.compress(b"hello " * 500),
        media_type="text/plain",
        headers={"content-encoding": "gzip"},
    )


async def status(request: Request) -> Response:
    return Response(status_code=int(request.path_params["code"]), content=b"")


async def echo_socket(websocket: WebSocket) -> None:
    wanted = websocket.scope.get("subprotocols") or []
    await websocket.accept(subprotocol=wanted[0] if wanted else None)
    await websocket.send_text(f"origin={websocket.headers.get('origin')}")
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("text") is not None:
                await websocket.send_text("echo:" + message["text"])
            else:
                await websocket.send_bytes(b"echo:" + message["bytes"])
    except RuntimeError:
        return


async def closing_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.close(code=4001, reason="going away")


UPSTREAM_ROUTES = [
    Route("/", page),
    Route("/health", health),
    Route("/echo", echo, methods=["GET", "POST", "PUT"]),
    Route("/echo/{rest:path}", echo),
    Route("/redirect", redirect),
    Route("/cookies", cookies),
    Route("/stream", stream),
    Route("/compressed", compressed),
    Route("/status/{code:int}", status),
    WebSocketRoute("/ws", echo_socket),
    WebSocketRoute("/closing", closing_socket),
    Route("/app/hello", echo),
]


class Upstream:
    """A server the tests put Cornea's proxy in front of."""

    def __init__(self) -> None:
        self.socket = socket.create_server(("127.0.0.1", 0))
        self.port = self.socket.getsockname()[1]
        config = uvicorn.Config(Starlette(routes=UPSTREAM_ROUTES), log_level="error")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, args=([self.socket],), daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "Upstream":
        self.thread.start()
        while not self.server.started:
            time.sleep(0.01)
        return self

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(10)
        self.socket.close()


@pytest.fixture(scope="module")
def upstream() -> Iterator[Upstream]:
    """One upstream for the whole file: it keeps no state between tests."""
    server = Upstream().start()
    try:
        yield server
    finally:
        server.stop()


class Browser:
    """A signed-in client of a running Cornea shell."""

    def __init__(self, shell: Shell) -> None:
        self.shell = shell
        connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=10)
        connection.request("GET", f"/?cornea_token={shell.app.state.bootstrap_token}")
        self.session = (connection.getresponse().getheader("Set-Cookie") or "").split(";")[0]
        connection.close()

    def request(
        self,
        path: str,
        method: str = "GET",
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        signed_in: bool = True,
    ) -> tuple[int, http.client.HTTPMessage, bytes]:
        sent = {"Origin": self.shell.base_url, **(headers or {})}
        if signed_in:
            extra = sent.get("Cookie")
            sent["Cookie"] = f"{self.session}; {extra}" if extra else self.session
        connection = http.client.HTTPConnection("127.0.0.1", self.shell.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=sent)
            response = connection.getresponse()
            return response.status, response.msg, response.read()
        finally:
            connection.close()

    def json(self, path: str, method: str = "GET", **options: Any) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self.request(path, method, **options)[2])
        return result


@pytest.fixture(scope="module")
def proxied(upstream: Upstream) -> Iterator[tuple[Shell, Browser]]:
    """One signed-in shell for the tests that only read; others build their own."""
    shell = Shell(Url(upstream.url, mode="proxy"), window=None)
    with shell:
        yield shell, Browser(shell)


# ----- the page and the security layer ----------------------------------------------------------


def test_the_upstream_page_is_served_from_cornea(proxied: tuple[Shell, Browser]) -> None:
    shell, browser = proxied

    status, headers, body = browser.request("/")

    assert (status, body) == (200, b"<html>upstream page</html>")
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert headers["Content-Security-Policy"] == Security().csp
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert shell.url.startswith(f"http://127.0.0.1:{shell.port}/?cornea_token=")


def test_the_proxied_page_needs_a_session(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    assert browser.request("/", signed_in=False)[0] == 401
    assert browser.request("/echo", signed_in=False)[0] == 401


def test_other_hosts_are_refused_before_the_upstream_is_reached(
    proxied: tuple[Shell, Browser],
) -> None:
    _, browser = proxied

    assert browser.request("/", headers={"Host": "evil.example"})[0] == 403


def test_state_changing_requests_still_need_a_matching_origin(
    proxied: tuple[Shell, Browser],
) -> None:
    shell, browser = proxied
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=10)
    connection.request("POST", "/echo", body=b"x", headers={"Cookie": browser.session})
    refused = connection.getresponse().status
    connection.close()

    assert refused == 403
    assert browser.request("/echo", "POST", body=b"x")[0] == 200


def test_cornea_keeps_its_own_routes(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    assert browser.request("/health", signed_in=False)[2] == b'{"status":"ok"}'
    assert browser.json("/api/window")["title"] == "Cornea Shell"
    assert browser.request("/api/unknown")[2] == b'{"error":"Not Found"}'
    assert browser.json("/api/bridge/platform_info", "POST")["available"] is True


# ----- what is forwarded ------------------------------------------------------------------------


def test_the_path_and_query_arrive_unchanged(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    seen = browser.json("/echo/a%20b/c?x=1&y=%2F&z=")

    assert seen["path"] == "/echo/a%20b/c"
    assert seen["query"] == "x=1&y=%2F&z="


def test_a_t_parameter_of_the_upstream_is_not_taken_for_the_token(
    proxied: tuple[Shell, Browser],
) -> None:
    """Vite adds `?t=<timestamp>` to hot-reloaded files; Cornea must pass it on, not refuse it."""
    _, browser = proxied

    status, _, body = browser.request("/echo?t=1793482450924&other=1")

    assert status == 200
    assert json.loads(body)["query"] == "t=1793482450924&other=1"


def test_the_upstream_sees_itself_as_the_origin(
    proxied: tuple[Shell, Browser], upstream: Upstream
) -> None:
    shell, browser = proxied

    seen = browser.json(
        "/echo",
        headers={"Referer": f"{shell.base_url}/page?q=1", "X-Custom": "kept", "Accept": "text/x"},
    )["headers"]

    assert seen["host"] == f"127.0.0.1:{upstream.port}"
    assert seen["origin"] == upstream.url
    assert seen["referer"] == f"{upstream.url}/page?q=1"
    assert seen["x-custom"] == "kept"
    assert seen["accept"] == "text/x"


def test_the_session_cookie_never_reaches_the_upstream(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    mixed = browser.json("/echo", headers={"Cookie": "theme=dark; other=1"})["headers"]
    alone = browser.json("/echo")["headers"]

    assert mixed["cookie"] == "theme=dark; other=1"
    assert "cornea_session" not in mixed["cookie"]
    assert "cookie" not in alone


def test_a_request_body_is_streamed_to_the_upstream(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied
    payload = b"0123456789" * 100_000

    small = browser.json("/echo", "POST", body=b"hello", headers={"Content-Type": "text/plain"})
    large = browser.json("/echo", "PUT", body=payload)

    assert (small["method"], small["body_length"], small["body_start"]) == ("POST", 5, "hello")
    assert (large["method"], large["body_length"]) == ("PUT", len(payload))


def test_requests_without_a_body_send_none(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    seen = browser.json("/echo")

    assert seen["body_length"] == 0
    assert "content-length" not in seen["headers"]
    assert "transfer-encoding" not in seen["headers"]


# ----- what comes back --------------------------------------------------------------------------


def test_redirects_are_passed_on_and_made_relative(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    status, headers, _ = browser.request("/redirect")

    assert status == 302
    assert headers["Location"] == "/target?x=1"


def test_cookies_lose_their_domain_and_keep_the_rest(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    _, headers, _ = browser.request("/cookies")

    cookies = headers.get_all("Set-Cookie")
    assert cookies == ["a=1; Path=/", "b=2; Path=/; HttpOnly"]


def test_streamed_responses_arrive_whole(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    assert browser.request("/stream")[2] == b"chunk0;chunk1;chunk2;chunk3;"


def test_compressed_bodies_pass_through_compressed(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    _, headers, body = browser.request("/compressed", headers={"Accept-Encoding": "gzip"})

    assert headers["Content-Encoding"] == "gzip"
    assert gzip.decompress(body) == b"hello " * 500


@pytest.mark.parametrize("code", [201, 204, 304, 404, 500])
def test_statuses_pass_through(code: int, proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    assert browser.request(f"/status/{code}")[0] == code


def test_head_requests_have_no_body(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    status, headers, body = browser.request("/", "HEAD")

    assert (status, body) == (200, b"")
    assert headers["Content-Type"].startswith("text/html")


def test_the_server_and_date_headers_are_not_doubled(proxied: tuple[Shell, Browser]) -> None:
    _, browser = proxied

    _, headers, _ = browser.request("/")

    assert len(headers.get_all("Date") or []) == 1
    assert len(headers.get_all("Server") or []) == 1


@pytest.fixture
def dead_upstream() -> Iterator[int]:
    """A port that accepts connections and hangs up at once, like a server that has crashed.

    (A closed port would do, but Windows takes about two seconds to refuse a connection to one.)
    """
    listener = socket.create_server(("127.0.0.1", 0))
    stop = threading.Event()

    def hang_up() -> None:
        listener.settimeout(0.1)
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                continue
            connection.close()

    thread = threading.Thread(target=hang_up, daemon=True)
    thread.start()
    try:
        yield int(listener.getsockname()[1])
    finally:
        stop.set()
        thread.join(5)
        listener.close()


def test_an_unreachable_upstream_is_a_bad_gateway_page(dead_upstream: int) -> None:
    shell = Shell(Url(f"http://127.0.0.1:{dead_upstream}", mode="proxy"), window=None)

    with shell:
        status, headers, body = Browser(shell).request("/")

    assert status == 502
    assert headers["Content-Type"].startswith("text/html")
    assert f"http://127.0.0.1:{dead_upstream}".encode() in body
    assert b"Traceback" not in body


def test_an_upstream_path_prefix_is_kept(upstream: Upstream) -> None:
    shell = Shell(Url(f"{upstream.url}/app/", mode="proxy"), window=None)

    with shell:
        seen = Browser(shell).json("/hello")

    assert seen["path"] == "/app/hello"


# ----- WebSockets -------------------------------------------------------------------------------


def socket_url(shell: Shell, path: str) -> str:
    return f"ws://127.0.0.1:{shell.port}{path}"


def test_websocket_messages_go_both_ways(
    proxied: tuple[Shell, Browser], upstream: Upstream
) -> None:
    shell, browser = proxied

    with connect(
        socket_url(shell, "/ws"),
        additional_headers={"Cookie": browser.session, "Origin": shell.base_url},
        proxy=None,
    ) as client:
        assert client.recv() == f"origin={upstream.url}"
        client.send("hi")
        assert client.recv() == "echo:hi"
        client.send(b"\x00\x01")
        assert client.recv() == b"echo:\x00\x01"


def test_websocket_subprotocols_are_negotiated(proxied: tuple[Shell, Browser]) -> None:
    shell, browser = proxied

    with connect(
        socket_url(shell, "/ws"),
        additional_headers={"Cookie": browser.session, "Origin": shell.base_url},
        subprotocols=["vite-hmr"],  # type: ignore[list-item]
        proxy=None,
    ) as client:
        assert client.subprotocol == "vite-hmr"


def test_a_websocket_close_code_reaches_the_client(proxied: tuple[Shell, Browser]) -> None:
    shell, browser = proxied

    with connect(
        socket_url(shell, "/closing"),
        additional_headers={"Cookie": browser.session, "Origin": shell.base_url},
        proxy=None,
    ) as client:
        with pytest.raises(ConnectionClosed):
            client.recv(timeout=5)
        assert client.protocol.close_code == 4001


def test_websockets_need_a_session_and_an_origin(proxied: tuple[Shell, Browser]) -> None:
    shell, browser = proxied

    for headers in (
        {"Origin": shell.base_url},
        {"Cookie": browser.session},
        {"Cookie": browser.session, "Origin": "http://evil.example"},
    ):
        with pytest.raises(InvalidStatus) as refused:
            connect(socket_url(shell, "/ws"), additional_headers=headers, proxy=None)
        assert refused.value.response.status_code == 403


def test_a_websocket_to_a_dead_upstream_is_closed(dead_upstream: int) -> None:
    shell = Shell(Url(f"http://127.0.0.1:{dead_upstream}", mode="proxy"), window=None)

    with shell:
        browser = Browser(shell)
        with pytest.raises(InvalidStatus) as refused:
            connect(
                socket_url(shell, "/ws"),
                additional_headers={"Cookie": browser.session, "Origin": shell.base_url},
                proxy=None,
            )
        assert refused.value.response.status_code == 403


# ----- the shell with a proxied source ----------------------------------------------------------


def test_a_proxied_address_can_be_frameless_and_headless(upstream: Upstream) -> None:
    Shell(Url(upstream.url, mode="proxy"), window=Window(frameless=True))
    Shell(Url(upstream.url, mode="proxy"), window=None)


def test_a_proxied_address_has_a_local_server(upstream: Upstream) -> None:
    shell = Shell(Url(upstream.url, mode="proxy"), window=None)

    assert not shell.is_direct
    with shell:
        assert shell.running
        assert shell.base_url.startswith("http://127.0.0.1:")


def test_stopping_the_shell_closes_the_upstream_connections(upstream: Upstream) -> None:
    shell = Shell(Url(upstream.url, mode="proxy"), window=None)
    with shell:
        Browser(shell).request("/")
        proxy = shell.app.state.proxy
        assert not proxy._client.is_closed

    assert proxy._client.is_closed


def test_the_window_state_works_with_a_proxied_frameless_window(upstream: Upstream) -> None:
    shell = Shell(Url(upstream.url, mode="proxy"), window=None)
    with shell:
        browser = Browser(shell)

        assert browser.json("/api/window")["frameless"] is False
        assert browser.json("/api/window/maximize", "POST") == {"ok": True}
        assert browser.json("/api/window")["maximized"] is True


# ----- the pieces -------------------------------------------------------------------------------


def test_the_session_cookie_is_removed_from_a_cookie_header() -> None:
    assert without_session_cookie("cornea_session=abc") is None
    assert without_session_cookie("a=1; cornea_session=abc; b=2") == "a=1; b=2"
    assert without_session_cookie("a=1;b=2") == "a=1; b=2"
    assert without_session_cookie("") is None
    assert without_session_cookie("my_cornea_session=1") == "my_cornea_session=1"


def test_hop_by_hop_headers_are_not_forwarded() -> None:
    proxy = ProxyApp("http://localhost:5173")
    scope = {
        "headers": [(name.encode(), b"x") for name in (*HOP_BY_HOP, "host", "accept")],
    }

    forwarded = [name for name, _ in proxy._request_headers(scope)]

    assert forwarded == ["accept"]


def test_response_headers_are_cleaned() -> None:
    proxy = ProxyApp("http://localhost:5173")

    cleaned = proxy._response_headers(
        [
            ("Connection", "close"),
            ("Transfer-Encoding", "chunked"),
            ("Date", "now"),
            ("Server", "x"),
            ("Location", "http://localhost:5173"),
            ("Set-Cookie", "a=1; domain=localhost; Path=/"),
            ("X-Keep", "yes"),
        ]
    )

    assert cleaned == [
        (b"location", b"/"),
        (b"set-cookie", b"a=1; Path=/"),
        (b"x-keep", b"yes"),
    ]


def test_a_location_on_another_site_is_left_alone() -> None:
    proxy = ProxyApp("http://localhost:5173")

    cleaned = proxy._response_headers([("Location", "https://example.com/login")])

    assert cleaned == [(b"location", b"https://example.com/login")]


def test_the_proxy_extra_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "httpx", None)

    with pytest.raises(ImportError, match=r"cornea-shell\[proxy\]"):
        ProxyApp("http://localhost:5173")


def test_the_target_uses_the_raw_path_and_the_base_path() -> None:
    proxy = ProxyApp("http://localhost:5173/base/")

    assert proxy._target({"raw_path": b"/a%20b", "path": "/a b", "query_string": b"q=1"}) == (
        "http://localhost:5173/base/a%20b?q=1"
    )
    assert proxy._target({"path": "/x", "query_string": b""}) == "http://localhost:5173/base/x"
