import re
from typing import Any

import pytest

from asgi_client import AsgiClient, Response
from cornea import NONCE_CSP, Security
from cornea.core.security import security as security_module
from cornea.core.security.security import (
    NONCE_SCOPE_KEY,
    SecurityMiddleware,
    SessionGate,
    add_nonce_meta,
)

HOST = "127.0.0.1:8000"
TOKEN = "start-up-token"  # noqa: S105
PAGE = b"<!doctype html><html><head><title>x</title></head><body>hi</body></html>"
seen: dict[str, Any] = {}


def page_app(
    body: bytes = PAGE,
    *,
    content_type: bytes = b"text/html; charset=utf-8",
    status: int = 200,
    extra: tuple[tuple[bytes, bytes], ...] = (),
    chunks: int = 1,
) -> Any:
    async def app(scope: Any, receive: Any, send: Any) -> None:
        seen["nonce"] = scope.get(NONCE_SCOPE_KEY)
        seen["headers"] = dict(scope["headers"])
        headers = [
            (b"content-type", content_type),
            (b"content-length", str(len(body)).encode()),
            (b"etag", b'"v1"'),
            *extra,
        ]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        step = max(1, len(body) // chunks)
        parts = [body[i : i + step] for i in range(0, len(body), step)] or [b""]
        for number, part in enumerate(parts):
            await send(
                {
                    "type": "http.response.body",
                    "body": part,
                    "more_body": number < len(parts) - 1,
                }
            )

    return app


def get(
    app: Any, security: Security | None = None, headers: dict[str, str] | None = None
) -> Response:
    gate = SessionGate(TOKEN)
    middleware = SecurityMiddleware(app, gate, security or Security(csp=NONCE_CSP), [HOST])
    client = AsgiClient(middleware)
    session = gate.redeem(TOKEN)
    cookie = f"cornea_session_8000={session}"
    return client.request("/", cookie=cookie, headers=headers)


def nonce_in_header(response: Response) -> str:
    match = re.search(r"'nonce-([^']+)'", response.header("content-security-policy") or "")
    assert match is not None
    return match.group(1)


def test_the_header_and_the_page_carry_the_same_nonce() -> None:
    response = get(page_app())
    nonce = nonce_in_header(response)

    assert f'<meta name="cornea-csp-nonce" content="{nonce}">' in response.body.decode()
    assert response.body.startswith(b"<!doctype html><html><head><meta ")
    assert "{nonce}" not in response.header("content-security-policy")  # type: ignore[operator]


def test_each_response_gets_a_new_nonce() -> None:
    assert nonce_in_header(get(page_app())) != nonce_in_header(get(page_app()))


def test_the_app_can_read_the_nonce() -> None:
    response = get(page_app())

    assert seen["nonce"] == nonce_in_header(response)


def test_the_length_is_corrected_and_the_page_is_not_cached() -> None:
    response = get(page_app())

    assert response.header("content-length") == str(len(response.body))
    assert len(response.body) > len(PAGE)
    assert response.header("cache-control") == "no-store"
    assert response.header("etag") is None


def test_a_page_in_several_chunks_is_put_together() -> None:
    response = get(page_app(chunks=5))

    assert response.body.count(b"cornea-csp-nonce") == 1
    assert response.body.endswith(b"<body>hi</body></html>")


def test_packed_pages_are_not_asked_for() -> None:
    get(page_app(), headers={"accept-encoding": "gzip, br"})

    assert b"accept-encoding" not in seen["headers"]


def test_a_packed_page_is_left_alone() -> None:
    response = get(page_app(extra=((b"content-encoding", b"gzip"),)))

    assert response.body == PAGE
    assert response.header("etag") == '"v1"'


@pytest.mark.parametrize(
    "app",
    [
        page_app(b'{"a": 1}', content_type=b"application/json"),
        page_app(b"missing", status=404),
    ],
)
def test_other_responses_are_left_alone(app: Any) -> None:
    response = get(app)

    assert b"cornea-csp-nonce" not in response.body
    assert response.header("etag") == '"v1"'
    assert nonce_in_header(response)  # the header still has a nonce, it is just not used


def test_a_page_with_no_head_gets_one() -> None:
    response = get(page_app(b"<html><body>x</body></html>"))

    assert response.body.startswith(b"<html><head><meta name=")
    assert b"</head><body>x</body>" in response.body


def test_a_page_with_nowhere_for_the_tag_is_left_alone() -> None:
    assert add_nonce_meta(b"just text", "n") is None
    assert get(page_app(b"just text")).body == b"just text"


def test_a_head_tag_with_attributes_and_other_case_is_found() -> None:
    page = add_nonce_meta(b'<HEAD lang="en"><title>x</title>', "abc")

    assert page == b'<HEAD lang="en"><meta name="cornea-csp-nonce" content="abc"><title>x</title>'


def test_a_page_too_big_to_hold_is_sent_as_it_is(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security_module, "MAX_NONCE_PAGE", 10)

    response = get(page_app(chunks=4))

    assert response.body == PAGE


def test_without_a_placeholder_nothing_changes() -> None:
    response = get(page_app(), Security())

    assert response.body == PAGE
    assert seen["nonce"] is None
    assert response.header("etag") == '"v1"'
