from collections.abc import Callable
from http.cookies import CookieError, SimpleCookie
from typing import Any

import pytest

from asgi_client import AsgiClient
from cornea import Security
from cornea.core.security.security import (
    BOOTSTRAP_PARAM,
    SESSION_COOKIE_PATTERN,
    SecurityMiddleware,
    SessionGate,
    new_token,
    session_cookie_name,
)

HOST = "127.0.0.1:8000"
ORIGIN = "http://127.0.0.1:8000"
TOKEN = "start-up-token"  # noqa: S105


async def sample_app(scope: Any, receive: Any, send: Any) -> None:
    """Answers every request with 200, or accepts a WebSocket."""
    if scope["type"] == "websocket":
        await send({"type": "websocket.accept"})
        return
    headers = [(b"content-type", b"text/plain")]
    if scope["path"] == "/own-policy":
        headers.append((b"content-security-policy", b"default-src 'none'"))
    if scope["path"] == "/sloppy":
        headers.append((b"x-content-type-options", b"anything"))
    await send({"type": "http.response.start", "status": 200, "headers": headers})
    await send({"type": "http.response.body", "body": b"ok"})


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def make_client(clock: Clock) -> Callable[..., AsgiClient]:
    def build(security: Security | None = None, ttl: float = 60.0) -> AsgiClient:
        gate = SessionGate(TOKEN, ttl=ttl, clock=clock)
        middleware = SecurityMiddleware(sample_app, gate, security, allowed_hosts=[HOST])
        return AsgiClient(middleware)

    return build


def sign_in(client: AsgiClient) -> str:
    """Redeem the token and return the ``Cookie`` header value for later requests."""
    response = client.request("/", query=f"{BOOTSTRAP_PARAM}={TOKEN}")
    assert response.status == 303
    return (response.header("set-cookie") or "").split(";")[0]


# ----- session gate ---------------------------------------------------------------------------


def test_new_token_is_unique_and_long() -> None:
    assert new_token() != new_token()
    assert len(new_token()) >= 40


def test_token_can_be_redeemed_once(clock: Clock) -> None:
    gate = SessionGate(TOKEN, clock=clock)

    session_id = gate.redeem(TOKEN)

    assert session_id is not None
    assert gate.is_valid(session_id)
    assert gate.redeem(TOKEN) is None


def test_wrong_token_does_not_use_up_the_real_one(clock: Clock) -> None:
    gate = SessionGate(TOKEN, clock=clock)

    assert gate.redeem("wrong") is None
    assert gate.redeem(TOKEN) is not None


def test_token_expires_after_ttl(clock: Clock) -> None:
    gate = SessionGate(TOKEN, ttl=30, clock=clock)
    clock.now += 31

    assert gate.redeem(TOKEN) is None


def test_token_is_valid_right_up_to_ttl(clock: Clock) -> None:
    gate = SessionGate(TOKEN, ttl=30, clock=clock)
    clock.now += 30

    assert gate.redeem(TOKEN) is not None


@pytest.mark.parametrize("session_id", [None, "", "unknown"])
def test_unknown_sessions_are_not_valid(session_id: str | None, clock: Clock) -> None:
    assert not SessionGate(TOKEN, clock=clock).is_valid(session_id)


# ----- host -----------------------------------------------------------------------------------


def test_unexpected_host_is_rejected(make_client: Callable[..., AsgiClient]) -> None:
    response = make_client().request("/health", host="evil.example")

    assert response.status == 403
    assert b"Unexpected Host" in response.body


def test_missing_host_is_rejected(make_client: Callable[..., AsgiClient]) -> None:
    assert make_client().request("/health", host=None).status == 403


def test_host_match_ignores_case(make_client: Callable[..., AsgiClient]) -> None:
    assert make_client().request("/health", host="127.0.0.1:8000".upper()).status == 200


def test_extra_hosts_come_from_security_settings(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client(Security(allowed_hosts=("app.local:9000",)))

    assert client.request("/health", host="app.local:9000").status == 200


def test_allow_host_adds_the_bound_address(clock: Clock) -> None:
    middleware = SecurityMiddleware(sample_app, SessionGate(TOKEN, clock=clock))
    client = AsgiClient(middleware)
    assert client.request("/health").status == 403

    middleware.allow_host("127.0.0.1:8000")

    assert client.request("/health").status == 200


# ----- sign-in --------------------------------------------------------------------------------


def test_requests_without_a_session_are_rejected(make_client: Callable[..., AsgiClient]) -> None:
    response = make_client().request("/")

    assert response.status == 401
    assert b"Not signed in" in response.body
    assert response.header("content-type") == "application/json"


def test_health_is_public_by_default(make_client: Callable[..., AsgiClient]) -> None:
    assert make_client().request("/health").status == 200


def test_public_paths_can_be_changed(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client(Security(public_paths=("/ping", "/assets/")))

    assert client.request("/ping").status == 200
    assert client.request("/assets/app.js").status == 200
    assert client.request("/health").status == 401
    assert client.request("/assetsx").status == 401


def test_bootstrap_sets_cookie_and_redirects(make_client: Callable[..., AsgiClient]) -> None:
    response = make_client().request("/", query=f"{BOOTSTRAP_PARAM}={TOKEN}")

    cookie = response.header("set-cookie") or ""
    assert response.status == 303
    assert response.header("location") == "/"
    assert cookie.startswith("cornea_session_8000=")
    assert {"HttpOnly", "Path=/", "SameSite=Strict"} <= set(cookie.split("; "))
    assert "Max-Age" not in cookie
    assert "Expires" not in cookie
    assert "Secure" not in cookie


def test_cookie_samesite_follows_settings(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client(Security(cookie_samesite="lax"))

    response = client.request("/", query=f"{BOOTSTRAP_PARAM}={TOKEN}")

    assert "SameSite=Lax" in (response.header("set-cookie") or "")


def test_redirect_removes_only_the_token(make_client: Callable[..., AsgiClient]) -> None:
    response = make_client().request("/docs", query=f"a=1&{BOOTSTRAP_PARAM}={TOKEN}&b=two")

    assert response.header("location") == "/docs?a=1&b=two"


def test_redirect_never_leaves_the_site(make_client: Callable[..., AsgiClient]) -> None:
    response = make_client().request("//evil.example/x", query=f"{BOOTSTRAP_PARAM}={TOKEN}")

    assert response.header("location") == "/evil.example/x"


def test_session_cookie_unlocks_every_route(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client()
    cookie = sign_in(client)

    assert client.request("/", cookie=cookie).status == 200
    assert client.request("/deep/page", cookie=cookie).body == b"ok"


def test_token_cannot_be_used_twice(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client()
    sign_in(client)

    response = client.request("/", query=f"{BOOTSTRAP_PARAM}={TOKEN}")

    assert response.status == 403
    assert b"not valid" in response.body


def test_wrong_token_is_rejected(make_client: Callable[..., AsgiClient]) -> None:
    response = make_client().request("/", query=f"{BOOTSTRAP_PARAM}=nope")

    assert response.status == 403
    assert response.header("set-cookie") is None


def test_expired_token_is_rejected(make_client: Callable[..., AsgiClient], clock: Clock) -> None:
    client = make_client(ttl=10)
    clock.now += 11

    assert client.request("/", query=f"{BOOTSTRAP_PARAM}={TOKEN}").status == 403


def test_token_ttl_is_taken_from_the_gate(
    make_client: Callable[..., AsgiClient], clock: Clock
) -> None:
    client = make_client(ttl=600)
    clock.now += 599

    assert client.request("/", query=f"{BOOTSTRAP_PARAM}={TOKEN}").status == 303


def test_token_is_ignored_on_unsafe_methods(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client()

    response = client.request("/", method="POST", origin=ORIGIN, query=f"{BOOTSTRAP_PARAM}={TOKEN}")

    assert response.status == 401
    assert sign_in(client)


def test_forged_cookie_is_rejected(make_client: Callable[..., AsgiClient]) -> None:
    response = make_client().request("/", cookie="cornea_session_8000=forged")

    assert response.status == 401


def test_malformed_cookie_header_is_rejected(make_client: Callable[..., AsgiClient]) -> None:
    assert make_client().request("/", cookie='=;"\\').status == 401


def test_cookie_parsing_errors_mean_not_signed_in(
    make_client: Callable[..., AsgiClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: SimpleCookie, rawdata: str) -> None:
        raise CookieError("bad cookie")

    monkeypatch.setattr(SimpleCookie, "load", broken)

    assert make_client().request("/", cookie="anything=1").status == 401


# ----- origin ---------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_state_changing_requests_need_a_matching_origin(
    method: str, make_client: Callable[..., AsgiClient]
) -> None:
    client = make_client()
    cookie = sign_in(client)

    assert client.request("/x", method=method, cookie=cookie).status == 403
    assert (
        client.request("/x", method=method, cookie=cookie, origin="http://evil.example").status
        == 403
    )
    assert client.request("/x", method=method, cookie=cookie, origin=ORIGIN).status == 200


def test_origin_error_message(make_client: Callable[..., AsgiClient]) -> None:
    response = make_client().request("/x", method="POST")

    assert response.status == 403
    assert b"Unexpected Origin" in response.body


def test_missing_origin_can_be_allowed(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client(Security(require_origin=False))
    cookie = sign_in(client)

    assert client.request("/x", method="POST", cookie=cookie).status == 200
    assert (
        client.request("/x", method="POST", cookie=cookie, origin="http://evil.example").status
        == 403
    )


def test_safe_methods_ignore_origin(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client()
    cookie = sign_in(client)

    assert client.request("/", cookie=cookie, origin="http://evil.example").status == 200


def test_origin_must_belong_to_an_allowed_host(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client(Security(allowed_hosts=("app.local",)))
    cookie = sign_in(client)

    response = client.request("/x", method="POST", cookie=cookie, origin="https://app.local")

    assert response.status == 200


# ----- headers --------------------------------------------------------------------------------


def test_security_headers_are_added(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client()
    response = client.request("/", cookie=sign_in(client))

    assert (
        response.header("content-security-policy")
        == f"{Security().csp}; report-uri /api/csp-report"
    )
    assert response.header("x-content-type-options") == "nosniff"
    assert response.header("referrer-policy") == "no-referrer"
    assert response.header("cross-origin-opener-policy") == "same-origin"
    assert response.header("cross-origin-resource-policy") == "same-origin"
    assert response.header("access-control-allow-origin") is None


def test_error_responses_carry_the_headers_too(make_client: Callable[..., AsgiClient]) -> None:
    response = make_client().request("/")

    assert response.status == 401
    assert response.header("x-content-type-options") == "nosniff"
    assert response.header("content-security-policy") is not None


def test_csp_is_configurable(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client(Security(csp="default-src 'self'; style-src 'self' 'unsafe-inline'"))

    response = client.request("/", cookie=sign_in(client))

    assert response.header("content-security-policy") == (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; report-uri /api/csp-report"
    )


def test_a_policy_that_names_its_own_reporting_is_left_alone(
    make_client: Callable[..., AsgiClient],
) -> None:
    client = make_client(Security(csp="default-src 'self'; report-uri /my-reports"))

    response = client.request("/", cookie=sign_in(client))

    assert (
        response.header("content-security-policy") == "default-src 'self'; report-uri /my-reports"
    )


def test_a_policy_set_by_the_app_is_kept(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client()

    response = client.request("/own-policy", cookie=sign_in(client))

    assert response.values("content-security-policy") == ["default-src 'none'"]


def test_fixed_headers_cannot_be_weakened_by_the_app(
    make_client: Callable[..., AsgiClient],
) -> None:
    client = make_client()

    response = client.request("/sloppy", cookie=sign_in(client))

    assert response.values("x-content-type-options") == ["nosniff"]


def test_api_responses_are_not_cached(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client()
    cookie = sign_in(client)

    assert client.request("/api/items", cookie=cookie).header("cache-control") == "no-store"
    assert client.request("/api", cookie=cookie).header("cache-control") == "no-store"
    assert client.request("/apiary", cookie=cookie).header("cache-control") is None
    assert client.request("/", cookie=cookie).header("cache-control") is None


def test_api_prefix_follows_settings(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client(Security(api_prefix="/v1"))
    cookie = sign_in(client)

    assert client.request("/v1/x", cookie=cookie).header("cache-control") == "no-store"
    assert client.request("/api/x", cookie=cookie).header("cache-control") is None


# ----- WebSocket and other scopes -------------------------------------------------------------


def test_websocket_needs_a_session(make_client: Callable[..., AsgiClient]) -> None:
    result = make_client().websocket()

    assert result.closed_with == 1008
    assert not result.reached_app


def test_websocket_with_a_session_reaches_the_app(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client()

    result = client.websocket(cookie=sign_in(client))

    assert result.reached_app
    assert result.closed_with is None


def test_websocket_checks_host_and_origin(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client()
    cookie = sign_in(client)

    assert client.websocket(cookie=cookie, host="evil.example").closed_with == 1008
    assert client.websocket(cookie=cookie, origin="http://evil.example").closed_with == 1008
    assert client.websocket(cookie=cookie, origin=None).closed_with == 1008


def test_other_scopes_pass_through(clock: Clock) -> None:
    import asyncio

    seen: list[str] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["type"])

    middleware = SecurityMiddleware(app, SessionGate(TOKEN, clock=clock))

    asyncio.run(middleware({"type": "lifespan"}, None, None))  # type: ignore[arg-type]

    assert seen == ["lifespan"]


def test_a_plain_t_parameter_is_not_the_start_up_token(
    make_client: Callable[..., AsgiClient],
) -> None:
    """Dev servers add `?t=<timestamp>` to files; only `cornea_token` means anything to Cornea."""
    client = make_client()
    cookie = sign_in(client)

    assert BOOTSTRAP_PARAM == "cornea_token"
    assert client.request("/main.jsx", query="t=1793482450924", cookie=cookie).status == 200
    assert client.request("/main.jsx", query="t=1793482450924").status == 401


# ----- cookie name and idle expiry --------------------------------------------------------------


def test_cookie_name_carries_the_app_id_and_port() -> None:
    assert session_cookie_name("notes", "127.0.0.1:8765") == "cornea_notes_session_8765"
    assert session_cookie_name(None, "[::1]:9") == "cornea_session_9"
    assert session_cookie_name(None, "app.local") == "cornea_session"
    assert SESSION_COOKIE_PATTERN.match(session_cookie_name("a.b-c_d", "h:1"))


def test_cookie_of_another_port_is_not_accepted(make_client: Callable[..., AsgiClient]) -> None:
    client = make_client()
    session_id = client.request("/", query=f"{BOOTSTRAP_PARAM}={TOKEN}").header("set-cookie") or ""
    value = session_id.split(";")[0].split("=", 1)[1]

    assert client.request("/", cookie=f"cornea_session_9999={value}").status == 401
    assert client.request("/", cookie=f"cornea_session_8000={value}").status == 200


def test_idle_session_expires_but_activity_keeps_it(clock: Clock) -> None:
    gate = SessionGate(TOKEN, idle=100, clock=clock)
    session_id = gate.redeem(TOKEN)

    clock.now += 80
    assert gate.is_valid(session_id)
    clock.now += 80
    assert gate.is_valid(session_id)
    clock.now += 101
    assert not gate.is_valid(session_id)
