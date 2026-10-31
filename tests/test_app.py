import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter
from starlette.applications import Starlette

from asgi_client import AsgiClient
from cornea import Asgi, Security, Static, Url, Wsgi
from cornea.core.app import allow_host, create_app

HOST = "127.0.0.1:8000"
ORIGIN = "http://127.0.0.1:8000"


async def source_app(scope: Any, receive: Any, send: Any) -> None:
    """A mounted ASGI app that answers every path with its own marker."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"from-source:" + scope["path"].encode()})


def wsgi_source(environ: Any, start_response: Any) -> list[bytes]:
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"from-wsgi"]


def build(*args: Any, **kwargs: Any) -> tuple[Starlette, AsgiClient]:
    app = create_app(*args, **kwargs)
    allow_host(app, HOST)
    return app, AsgiClient(app)


def sign_in(app: Starlette, client: AsgiClient) -> str:
    response = client.request("/", query=f"cornea_token={app.state.bootstrap_token}")
    assert response.status == 303
    return (response.header("set-cookie") or "").split(";")[0]


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    (tmp_path / "app.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path


def hello_router() -> APIRouter:
    router = APIRouter()

    @router.get("/hello")
    def hello() -> dict[str, str]:
        return {"message": "hi"}

    @router.post("/echo")
    def echo() -> dict[str, bool]:
        return {"ok": True}

    return router


# ----- /health and the security layer ---------------------------------------------------------


def test_health_is_public_and_small() -> None:
    _, client = build()

    response = client.request("/health")

    assert response.status == 200
    assert json.loads(response.body) == {"status": "ok"}
    assert response.header("x-content-type-options") == "nosniff"


def test_everything_else_needs_a_session() -> None:
    _, client = build(routers=[hello_router()])

    assert client.request("/api/hello").status == 401
    assert client.request("/").status == 401


def test_unexpected_host_is_rejected_before_anything_else() -> None:
    _, client = build()

    assert client.request("/health", host="evil.example").status == 403


def test_bound_address_must_be_added() -> None:
    app = create_app()

    assert AsgiClient(app).request("/health").status == 403
    allow_host(app, "127.0.0.1:8000")
    assert AsgiClient(app).request("/health").status == 200


def test_allow_host_ignores_case() -> None:
    app = create_app()
    allow_host(app, "LocalHost:9")

    assert AsgiClient(app).request("/health", host="localhost:9").status == 200


def test_security_settings_are_applied() -> None:
    app, client = build(security=Security(public_paths=("/ping",), cookie_samesite="lax"))

    assert client.request("/health").status == 401
    response = client.request("/", query=f"cornea_token={app.state.bootstrap_token}")
    assert "SameSite=Lax" in (response.header("set-cookie") or "")


def test_bootstrap_token_is_generated_or_given() -> None:
    assert create_app().state.bootstrap_token != create_app().state.bootstrap_token
    assert create_app(bootstrap_token="mine").state.bootstrap_token == "mine"  # noqa: S105, S106


def test_token_ttl_comes_from_settings() -> None:
    app, client = build(security=Security(token_ttl=0.001))
    time.sleep(0.02)

    assert client.request("/", query=f"cornea_token={app.state.bootstrap_token}").status == 403


def test_no_cors_headers() -> None:
    _, client = build()

    assert client.request("/health").header("access-control-allow-origin") is None


def test_interactive_docs_are_off() -> None:
    app, client = build()
    cookie = sign_in(app, client)

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.request(path, cookie=cookie).status == 404


# ----- routers --------------------------------------------------------------------------------


def test_routers_are_mounted_under_the_api_prefix() -> None:
    app, client = build(routers=[hello_router()])
    cookie = sign_in(app, client)

    response = client.request("/api/hello", cookie=cookie)

    assert response.status == 200
    assert json.loads(response.body) == {"message": "hi"}
    assert response.header("cache-control") == "no-store"


def test_api_prefix_is_configurable() -> None:
    app, client = build(routers=[hello_router()], security=Security(api_prefix="/v1"))
    cookie = sign_in(app, client)

    assert client.request("/v1/hello", cookie=cookie).status == 200
    assert client.request("/api/hello", cookie=cookie).status == 404


def test_post_routes_need_origin() -> None:
    app, client = build(routers=[hello_router()])
    cookie = sign_in(app, client)

    assert client.request("/api/echo", method="POST", cookie=cookie).status == 403
    assert client.request("/api/echo", method="POST", cookie=cookie, origin=ORIGIN).status == 200


def test_unknown_api_paths_are_json_404s() -> None:
    app, client = build(routers=[hello_router()])
    cookie = sign_in(app, client)

    response = client.request("/api/nope", cookie=cookie)

    assert response.status == 404
    assert json.loads(response.body) == {"error": "Not Found"}
    assert client.request("/api", cookie=cookie).status == 404


# ----- sources --------------------------------------------------------------------------------


def test_no_source_serves_only_the_shell_routes() -> None:
    app, client = build()

    assert client.request("/", cookie=sign_in(app, client)).status == 404


def test_static_bundle_is_served(bundle: Path) -> None:
    app, client = build(Static(bundle))
    cookie = sign_in(app, client)

    assert client.request("/", cookie=cookie).body == b"<html>shell</html>"
    assert client.request("/app.js", cookie=cookie).body == b"console.log(1)"
    assert client.request("/missing.js", cookie=cookie).status == 404


def test_static_needs_a_session(bundle: Path) -> None:
    _, client = build(Static(bundle))

    assert client.request("/app.js").status == 401


def test_path_string_is_a_static_bundle(bundle: Path) -> None:
    app, client = build(str(bundle))

    assert client.request("/", cookie=sign_in(app, client)).status == 200


def test_missing_bundle_fails_at_creation(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"index.html"):
        create_app(Static(tmp_path))


def test_asgi_source_is_mounted() -> None:
    app, client = build(Asgi(source_app))
    cookie = sign_in(app, client)

    assert client.request("/some/page", cookie=cookie).body == b"from-source:/some/page"


def test_wsgi_source_is_mounted() -> None:
    app, client = build(Wsgi(wsgi_source))

    assert client.request("/", cookie=sign_in(app, client)).body == b"from-wsgi"


def test_mounted_apps_are_behind_the_security_layer() -> None:
    app, client = build(Asgi(source_app))

    assert client.request("/").status == 401
    assert client.request("/", host="evil.example").status == 403
    assert client.request("/x", cookie=sign_in(app, client)).header("referrer-policy") == (
        "no-referrer"
    )


def test_a_source_cannot_shadow_the_shell_routes() -> None:
    app, client = build(Asgi(source_app), routers=[hello_router()])
    cookie = sign_in(app, client)

    assert json.loads(client.request("/health").body) == {"status": "ok"}
    assert json.loads(client.request("/api/hello", cookie=cookie).body) == {"message": "hi"}
    unknown = client.request("/api/unknown", cookie=cookie)
    assert unknown.status == 404
    assert b"from-source" not in unknown.body


def test_direct_url_mounts_nothing() -> None:
    app, client = build(Url("http://localhost:5173"))

    assert client.request("/", cookie=sign_in(app, client)).status == 404


def test_bad_source_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="web source, path or URL"):
        create_app(42)  # type: ignore[arg-type]


def test_state_exposes_what_the_shell_needs() -> None:
    app = create_app()

    assert isinstance(app.state.allowed_hosts, set)
    assert app.state.security == Security()
    assert callable(app.state.gate.redeem)
