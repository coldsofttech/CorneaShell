"""Turning command line values into the settings and source objects of the Python API."""

import enum
import re
from pathlib import Path
from typing import Any

import typer

from cornea import (
    DEV_CSP,
    App,
    Asgi,
    Bridge,
    Process,
    Security,
    Server,
    Static,
    Url,
    WebSource,
    Window,
    Wsgi,
)

_URL = re.compile(r"^https?://", re.IGNORECASE)


class SameSite(enum.StrEnum):
    """The values ``--cookie-samesite`` accepts."""

    strict = "strict"
    lax = "lax"


class UrlMode(enum.StrEnum):
    """The values ``--mode`` accepts."""

    direct = "direct"
    proxy = "proxy"


class CspProfile(enum.StrEnum):
    """The values ``--csp-profile`` accepts."""

    strict = "strict"
    dev = "dev"


def parse_pair(text: str, flag: str, separator: str) -> tuple[int, int]:
    """``1200x800`` or ``100,50`` as two whole numbers."""
    parts = text.lower().split(separator)
    try:
        first, second = (int(part) for part in parts)
    except ValueError:
        example = "1200x800" if separator == "x" else "100,50"
        raise typer.BadParameter(f"{flag} looks like {example}, got {text!r}") from None
    return first, second


def build_source(
    *,
    argument: str | None,
    web_dist: Path | None,
    url: str | None,
    asgi: str | None,
    wsgi: str | None,
    app_dir: Path | None,
    package: str | None,
    package_path: str | None,
    spa: bool | None,
    hashed_prefix: list[str] | None,
    mode: UrlMode | None = None,
    run: str | None = None,
    run_cwd: Path | None = None,
    run_timeout: float | None = None,
) -> WebSource:
    """The one web source the flags describe. Anything that does not fit is an error."""
    if argument is not None:
        if _URL.match(argument):
            url = _only(url, argument, "SOURCE", "--url")
        else:
            web_dist = _only(web_dist, Path(argument), "SOURCE", "--web-dist")
    given = {
        "--web-dist": web_dist,
        "--url": url,
        "--asgi": asgi,
        "--wsgi": wsgi,
    }
    chosen = [flag for flag, value in given.items() if value is not None]
    if len(chosen) > 1:
        raise typer.BadParameter(f"give one web source, not {' and '.join(chosen)}")
    bundle_options = {
        "--package": package,
        "--package-path": package_path,
        "--spa/--no-spa": spa,
        "--hashed-prefix": hashed_prefix,
    }
    set_bundle = [flag for flag, value in bundle_options.items() if value is not None]
    if app_dir is not None and not (asgi or wsgi):
        raise typer.BadParameter("--app-dir only applies to --asgi and --wsgi")
    if mode is not None and url is None:
        raise typer.BadParameter("--mode only applies to an address (--url)")
    if run is None and (run_cwd is not None or run_timeout is not None):
        raise typer.BadParameter("--run-cwd and --run-timeout need --run")
    if run is not None:
        if web_dist is not None or asgi is not None or wsgi is not None:
            raise typer.BadParameter("--run starts the server of an address; it cannot be combined")
        if url is None:
            raise typer.BadParameter("--run needs the address it serves on: add --url ADDRESS")
        return Process(
            run,
            url=url,
            mode=mode.value if mode else "direct",
            **_given(cwd=run_cwd, timeout=run_timeout),
        )
    if set_bundle and chosen and chosen[0] != "--web-dist":
        raise typer.BadParameter(f"{', '.join(set_bundle)} only apply to a web bundle")
    if url is not None:
        return Url(url, mode=mode.value if mode else "direct")
    if asgi is not None:
        return Asgi(asgi, app_dir=app_dir)
    if wsgi is not None:
        return Wsgi(wsgi, app_dir=app_dir)
    return Static(
        **_given(
            path=web_dist,
            package=package,
            package_path=package_path,
            spa=spa,
            hashed_prefixes=tuple(hashed_prefix) if hashed_prefix else None,
        )
    )


def _only(current: Any, value: Any, name: str, flag: str) -> Any:
    if current is not None:
        raise typer.BadParameter(f"give one web source, not {name} and {flag}")
    return value


def _given(**values: Any) -> dict[str, Any]:
    """Only the values that were actually set, so the settings keep their own defaults."""
    return {name: value for name, value in values.items() if value is not None}


def build_server(*, host: str | None, port: int | None) -> Server:
    return Server(**_given(host=host, port=port))


def build_security(
    *,
    allowed_host: list[str] | None,
    csp: str | None,
    api_prefix: str | None,
    token_ttl: float | None,
    cookie_samesite: SameSite | None,
    public_path: list[str] | None,
    require_origin: bool | None,
    csp_profile: CspProfile | None = None,
) -> Security:
    if csp is not None and csp_profile is not None:
        raise typer.BadParameter("give --csp or --csp-profile, not both")
    return Security(
        **_given(
            allowed_hosts=tuple(allowed_host) if allowed_host else None,
            csp=DEV_CSP if csp_profile is CspProfile.dev else csp,
            api_prefix=api_prefix,
            token_ttl=token_ttl,
            cookie_samesite=cookie_samesite.value if cookie_samesite else None,
            public_paths=tuple(public_path) if public_path else None,
            require_origin=require_origin,
        )
    )


def build_app(
    *, app_id: str | None, single_instance: bool | None, remember_window: bool | None
) -> App:
    return App(
        **_given(id=app_id, single_instance=single_instance, remember_window=remember_window)
    )


def build_bridge(*, disable_action: list[str] | None) -> Bridge:
    return Bridge(**_given(disabled=tuple(disable_action) if disable_action else None))


def build_window(
    *,
    title: str | None,
    size: str | None,
    min_size: str | None,
    position: str | None,
    frameless: bool | None,
    resizable: bool | None,
    on_top: bool | None,
    context_menu: bool | None,
    devtools: bool | None,
    debug: bool | None,
    js_api: bool | None = None,
    icon: Path | None = None,
) -> Window:
    return Window(
        **_given(
            title=title,
            size=parse_pair(size, "--size", "x") if size else None,
            min_size=parse_pair(min_size, "--min-size", "x") if min_size else None,
            position=parse_pair(position, "--position", ",") if position else None,
            frameless=frameless,
            resizable=resizable,
            on_top=on_top,
            context_menu=context_menu,
            devtools=devtools,
            debug=debug,
            js_api=js_api,
            icon=icon,
        )
    )
