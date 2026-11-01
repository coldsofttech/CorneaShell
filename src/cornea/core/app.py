"""The application factory: security, the host's routers, ``/health`` and the web source."""

import os
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from cornea.core.bridge import ActionRegistry
from cornea.core.bridge_routes import router as bridge_router
from cornea.core.close_guard import CloseGuard
from cornea.core.config import Bridge, Security
from cornea.core.page_routes import router as page_router
from cornea.core.proxy import ProxyApp
from cornea.core.security import SecurityMiddleware, SessionGate, new_token
from cornea.core.sources import Asgi, Process, Static, Url, WebSource, Wsgi, coerce_source
from cornea.core.static import BundleFiles
from cornea.core.window_routes import router as window_router

_ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def create_app(
    source: WebSource | str | os.PathLike[str] | None = None,
    *,
    routers: Iterable[APIRouter] = (),
    security: Security | None = None,
    bridge: Bridge | None = None,
    bootstrap_token: str | None = None,
) -> FastAPI:
    """Build the FastAPI app that the shell serves.

    ``source`` is where the UI comes from; ``None`` gives an API-only app. The host's ``routers``
    are mounted under ``security.api_prefix``. The shell's own routes (the API prefix and
    ``/health``) always win over the source. The bootstrap token and the allowed-host set are on
    ``app.state`` for the shell; add the bound address with :func:`allow_host` once the port is
    known.

    Example:
        >>> app = create_app()
        >>> app.state.security.api_prefix
        '/api'
    """
    security = security or Security()
    web_source = coerce_source(source) if source is not None else None
    token = bootstrap_token or new_token()
    gate = SessionGate(token, ttl=security.token_ttl)
    allowed_hosts: set[str] = set()

    # The interactive docs are off: they would be one more surface on every mounted app.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)
    app.state.bootstrap_token = token
    app.state.gate = gate
    app.state.security = security
    app.state.allowed_hosts = allowed_hosts
    app.state.window = None  # set by the shell once a window exists
    app.state.close_guard = CloseGuard()
    settings = bridge or Bridge()
    app.state.actions = ActionRegistry(
        settings.disabled, open_files=settings.open_files, notifications=settings.notifications
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(window_router, prefix=security.api_prefix)
    app.include_router(bridge_router, prefix=security.api_prefix)
    app.include_router(page_router, prefix=security.api_prefix)
    for router in routers:
        app.include_router(router, prefix=security.api_prefix)
    _reserve_api_prefix(app, security.api_prefix)
    _mount_source(app, web_source)

    app.add_middleware(
        SecurityMiddleware, gate=gate, security=security, allowed_hosts=allowed_hosts
    )
    return app


def allow_host(app: FastAPI, host: str) -> None:
    """Accept requests whose ``Host`` is ``host``, for example ``127.0.0.1:8765``."""
    app.state.allowed_hosts.add(host.lower())


def _reserve_api_prefix(app: FastAPI, prefix: str) -> None:
    """Answer unknown API paths here, so a mounted source cannot take them over."""

    @app.api_route(prefix, methods=_ALL_METHODS, include_in_schema=False)
    @app.api_route(f"{prefix}/{{rest:path}}", methods=_ALL_METHODS, include_in_schema=False)
    def not_found(rest: str = "") -> JSONResponse:
        return JSONResponse({"error": "Not Found"}, status_code=404)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    proxy: ProxyApp | None = getattr(app.state, "proxy", None)
    if proxy is not None:
        await proxy.aclose()


def _mount_source(app: FastAPI, source: WebSource | None) -> None:
    if isinstance(source, Static):
        bundle = BundleFiles(
            str(source.resolve()), spa=source.spa, hashed_prefixes=source.hashed_prefixes
        )
        app.mount("/", bundle)
    elif isinstance(source, Asgi | Wsgi):
        app.mount("/", source.load())
    elif isinstance(source, Url) and source.mode == "proxy":
        proxy = ProxyApp(source.url)
        app.state.proxy = proxy
        app.mount("/", proxy)
    elif isinstance(source, Process):
        raise ValueError("a Process source is started by Shell; use Shell or run() for it")
    # A direct Url has nothing to mount: the window opens the address itself.
