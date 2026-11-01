"""Serving a built web bundle: content types, caching and the single-page-app fallback."""

from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

HASHED_CACHE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"

# The system's own table can be wrong (on Windows the registry may call .js "text/plain").
_MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".wasm": "application/wasm",
    ".woff2": "font/woff2",
}


def _is_page_request(path: str) -> bool:
    """A path with no file extension is a page route, not a missing file."""
    return "." not in PurePosixPath(path).name


class BundleFiles(StaticFiles):
    """Serves a bundle folder.

    Starlette's :class:`StaticFiles` already rejects paths that leave the folder (``..`` and
    symlinks), sets ETags and answers range requests. This adds the page fallback, the cache
    headers and the correct content types.
    """

    def __init__(
        self, directory: str, *, spa: bool = True, hashed_prefixes: tuple[str, ...] = ("assets/",)
    ) -> None:
        super().__init__(directory=directory, html=True)
        self.spa = spa
        self.hashed_prefixes = hashed_prefixes

    async def get_response(self, path: str, scope: Scope) -> Response:
        served = path
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not self.spa or not _is_page_request(path):
                raise
            served = "index.html"
            response = await super().get_response(served, scope)
        self._add_headers(response, served)
        return response

    def _add_headers(self, response: Response, path: str) -> None:
        normalized = path.replace("\\", "/")
        hashed = any(normalized.startswith(prefix) for prefix in self.hashed_prefixes)
        response.headers["Cache-Control"] = HASHED_CACHE if hashed else REVALIDATE
        media_type = _MEDIA_TYPES.get(PurePosixPath(normalized).suffix.lower())
        if media_type is not None:
            response.headers["Content-Type"] = media_type
