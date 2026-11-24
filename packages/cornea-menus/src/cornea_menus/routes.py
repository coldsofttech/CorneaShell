"""The routes of one :class:`~cornea_menus.service.Menus`: its definition, clicks and assets."""

import functools
import html
from importlib import resources
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from cornea_menus.model import THEMES, MenuError
from cornea_menus.service import MAX_PAGE_BYTES

if TYPE_CHECKING:
    from cornea_menus.service import Menus

SCRIPTS = frozenset({"menus.js", "frame.js"})


class ClickBody(BaseModel):
    """An entry the person chose."""

    id: str = Field(min_length=1, max_length=64)
    menu: str | None = Field(default=None, max_length=64)


@functools.cache
def _asset(path: str) -> bytes:
    node = resources.files("cornea_menus").joinpath("static")
    for part in path.split("/"):
        node = node.joinpath(part)
    return node.read_bytes()


def _frame_page(prefix: str, theme: str, title: str) -> str:
    base = f"{prefix}/menus"
    return (
        "<!doctype html>\n"
        '<html lang="en" data-cornea-frame>\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        f'<link rel="stylesheet" href="{base}/base.css">\n'
        f'<link rel="stylesheet" href="{base}/themes/{theme}.css">\n'
        f'<script src="{base}/frame.js" defer></script>\n'
        '</head>\n<body class="cm-frame-body"></body>\n</html>\n'
    )


def build_router(menus: "Menus") -> APIRouter:
    """The routes for ``menus``. Mounted under the API prefix, so a session is always needed."""
    router = APIRouter(prefix="/menus", tags=["menus"])

    @router.get("")
    def definition() -> dict[str, Any]:
        return menus.definition()

    @router.post("/click")
    def click(body: ClickBody) -> JSONResponse:
        try:
            return JSONResponse(menus.click(body.id, body.menu))
        except KeyError:
            # Unknown, disabled and hidden entries answer alike: a page learns nothing from it.
            return JSONResponse({"error": "That menu entry cannot be chosen."}, status_code=404)

    @router.post("/definition")
    async def define(request: Request) -> JSONResponse:
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_PAGE_BYTES:
            return JSONResponse({"error": "The menu is too large."}, status_code=413)
        raw = await request.body()
        if len(raw) > MAX_PAGE_BYTES:
            return JSONResponse({"error": "The menu is too large."}, status_code=413)
        try:
            import json

            menus.define_from_page(json.loads(raw))
        except PermissionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=403)
        except (MenuError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"ok": True, "version": menus.definition()["version"]})

    @router.get("/frame", include_in_schema=False)
    def frame(request: Request) -> Response:
        prefix = request.app.state.security.api_prefix
        return Response(_frame_page(prefix, menus.theme, "Cornea Shell"), media_type="text/html")

    @router.get("/base.css", include_in_schema=False)
    def base_css() -> Response:
        return Response(_asset("base.css"), media_type="text/css")

    @router.get("/themes/{name}.css", include_in_schema=False)
    def theme_css(name: str) -> Response:
        if name not in THEMES:
            raise HTTPException(status_code=404, detail="No such theme.")
        return Response(_asset(f"themes/{name}.css"), media_type="text/css")

    @router.get("/{script}", include_in_schema=False)
    def script(script: str, request: Request) -> Response:
        if script not in SCRIPTS:
            raise HTTPException(status_code=404, detail="Not found.")
        prefix = request.app.state.security.api_prefix
        source = _asset(script).decode("utf-8").replace("__API_PREFIX__", prefix)
        return Response(source, media_type="text/javascript")

    return router
