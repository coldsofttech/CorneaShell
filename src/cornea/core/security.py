"""Request checks that keep other local programs and web pages out of the local server.

Pure ASGI, so the same checks guard any mounted app (FastAPI, Flask, Django, a proxied server).
"""

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from collections.abc import Callable, Iterable
from http.cookies import CookieError, SimpleCookie
from urllib.parse import parse_qsl, quote, urlencode

from cornea.core.config import Security
from cornea.core.sources import AsgiApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

SESSION_COOKIE = "cornea_session"
BOOTSTRAP_PARAM = "cornea_token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
POLICY_VIOLATION = 1008
"""WebSocket close code for a refused handshake."""

_FIXED_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
)


def new_token() -> str:
    """A fresh, unguessable bootstrap token for the first URL."""
    return secrets.token_urlsafe(32)


def _digest(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()


class SessionGate:
    """Exchanges the one-time bootstrap token for session ids, and recognises those ids."""

    def __init__(
        self,
        bootstrap_token: str,
        *,
        ttl: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token: str | None = bootstrap_token
        self._clock = clock
        self._expires = clock() + ttl
        self._sessions: set[str] = set()
        self._lock = threading.Lock()

    def redeem(self, candidate: str) -> str | None:
        """Return a new session id for the bootstrap token, once; ``None`` for anything else."""
        with self._lock:
            token = self._token
            if token is None:
                return None
            if self._clock() > self._expires:
                self._token = None
                return None
            if not hmac.compare_digest(token.encode(), candidate.encode()):
                return None
            self._token = None
            session_id = secrets.token_urlsafe(32)
            self._sessions.add(_digest(session_id))
            return session_id

    def is_valid(self, session_id: str | None) -> bool:
        """Whether ``session_id`` was issued by :meth:`redeem`."""
        if not session_id:
            return False
        with self._lock:
            return _digest(session_id) in self._sessions


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", ()):
        if key == name:
            return str(value.decode("latin-1"))
    return None


def _session_id(scope: Scope) -> str | None:
    raw = "; ".join(
        value.decode("latin-1") for key, value in scope.get("headers", ()) if key == b"cookie"
    )
    if not raw:
        return None
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(raw)
    except CookieError:
        return None
    morsel = jar.get(SESSION_COOKIE)
    return morsel.value if morsel else None


async def _respond(
    send: Send, status: int, body: bytes, headers: Iterable[tuple[bytes, bytes]] = ()
) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-length", str(len(body)).encode()), *headers],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _refused(scope: Scope, reason: str, *, misconfigured: bool = False) -> None:
    """Log a refused request: the method and path, never the query (it can carry the token).

    A wrong Host or Origin usually means a setting is off (``allowed_hosts``), so it is a
    warning and shows without turning logging on. The rest is routine and stays at debug.
    """
    level = logging.WARNING if misconfigured else logging.DEBUG
    logger.log(
        level, "Refused %s %s: %s", scope.get("method", scope["type"]), scope["path"], reason
    )


async def _error(send: Send, status: int, message: str) -> None:
    body = json.dumps({"error": message}).encode()
    await _respond(send, status, body, [(b"content-type", b"application/json")])


class SecurityMiddleware:
    """Checks Host, Origin and the session cookie, and adds the security response headers."""

    def __init__(
        self,
        app: AsgiApp,
        gate: SessionGate,
        security: Security | None = None,
        allowed_hosts: Iterable[str] = (),
    ) -> None:
        """Guard ``app``. A ``set`` passed as ``allowed_hosts`` is shared, so additions count."""
        self.app = app
        self.gate = gate
        self.security = security or Security()
        hosts = allowed_hosts if isinstance(allowed_hosts, set) else set(allowed_hosts)
        hosts.update((*hosts, *self.security.allowed_hosts))
        lowered = {host.lower() for host in hosts}
        hosts.clear()
        hosts.update(lowered)
        self.allowed_hosts: set[str] = hosts

    def allow_host(self, host: str) -> None:
        """Accept requests whose ``Host`` is ``host``, for example ``127.0.0.1:8765``."""
        self.allowed_hosts.add(host.lower())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            await self._http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._websocket(scope, receive, send)
        else:
            await self.app(scope, receive, send)

    # ----- checks -----------------------------------------------------------------------------

    def _host_allowed(self, scope: Scope) -> bool:
        host = _header(scope, b"host")
        return host is not None and host.lower() in self.allowed_hosts

    def _origin_allowed(self, scope: Scope) -> bool:
        origin = _header(scope, b"origin")
        if origin is None:
            return not self.security.require_origin
        accepted = {
            f"{scheme}://{host}" for host in self.allowed_hosts for scheme in ("http", "https")
        }
        return origin.lower() in accepted

    def _is_public(self, path: str) -> bool:
        return any(
            path == entry or (entry.endswith("/") and path.startswith(entry))
            for entry in self.security.public_paths
        )

    def _signed_in(self, scope: Scope) -> bool:
        return self.gate.is_valid(_session_id(scope))

    # ----- HTTP -------------------------------------------------------------------------------

    async def _http(self, scope: Scope, receive: Receive, send: Send) -> None:
        send = self._with_security_headers(scope, send)
        if not self._host_allowed(scope):
            _refused(scope, "unexpected Host header", misconfigured=True)
            await _error(send, 403, "Unexpected Host")
            return
        method = scope["method"]
        if method in UNSAFE_METHODS and not self._origin_allowed(scope):
            _refused(scope, "unexpected Origin header", misconfigured=True)
            await _error(send, 403, "Unexpected Origin")
            return
        if method in {"GET", "HEAD"} and await self._bootstrap(scope, send):
            return
        if not self._is_public(scope["path"]) and not self._signed_in(scope):
            _refused(scope, "no valid session cookie")
            await _error(send, 401, "Not signed in")
            return
        await self.app(scope, receive, send)

    async def _bootstrap(self, scope: Scope, send: Send) -> bool:
        """Handle a request that carries the bootstrap token. Returns True when it answered."""
        pairs = parse_qsl(scope.get("query_string", b"").decode("latin-1"), keep_blank_values=True)
        tokens = [value for key, value in pairs if key == BOOTSTRAP_PARAM]
        if not tokens:
            return False
        session_id = self.gate.redeem(tokens[0])
        if session_id is None:
            _refused(scope, "the start-up token was not valid, already used, or expired")
            await _error(send, 403, "The start-up link is not valid")
            return True
        remaining = [(key, value) for key, value in pairs if key != BOOTSTRAP_PARAM]
        # One leading slash only: "//host" would be a redirect to another site.
        path = "/" + (scope.get("root_path", "") + scope["path"]).lstrip("/")
        location = quote(path, safe="/") + (f"?{urlencode(remaining)}" if remaining else "")
        cookie = (
            f"{SESSION_COOKIE}={session_id}; HttpOnly; Path=/; "
            f"SameSite={self.security.cookie_samesite.capitalize()}"
        )
        await _respond(
            send,
            303,
            b"",
            [(b"location", location.encode("latin-1")), (b"set-cookie", cookie.encode("latin-1"))],
        )
        return True

    def _with_security_headers(self, scope: Scope, send: Send) -> Send:
        api_prefix = self.security.api_prefix
        path = scope["path"]
        is_api = path == api_prefix or path.startswith(f"{api_prefix}/")
        fixed = list(_FIXED_HEADERS)
        if is_api:
            fixed.append((b"cache-control", b"no-store"))
        replaced = {name for name, _ in fixed}
        csp = self.security.csp.encode("latin-1")

        async def secured(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message.get("headers", ()) if k.lower() not in replaced
                ]
                # A response that sets its own policy (for example a stricter one) keeps it.
                if not any(k.lower() == b"content-security-policy" for k, _ in headers):
                    headers.append((b"content-security-policy", csp))
                message = {**message, "headers": [*headers, *fixed]}
            await send(message)

        return secured

    # ----- WebSocket --------------------------------------------------------------------------

    async def _websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        allowed = (
            self._host_allowed(scope)
            and self._origin_allowed(scope)
            and (self._is_public(scope["path"]) or self._signed_in(scope))
        )
        if not allowed:
            wrong_place = not (self._host_allowed(scope) and self._origin_allowed(scope))
            _refused(scope, "host, origin or session check failed", misconfigured=wrong_place)
            await receive()
            await send({"type": "websocket.close", "code": POLICY_VIOLATION})
            return
        await self.app(scope, receive, send)
