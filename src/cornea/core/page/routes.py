"""Routes for the page itself: its JavaScript client and the content security policy reports."""

import functools
import json
import logging
from importlib import resources
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)

MAX_REPORT_BYTES = 8192
REPORT_PATH = "/csp-report"
"""Where, under the API prefix, the browser sends reports of what the policy blocked."""
CLIENT_PATH = "/client.js"

router = APIRouter(tags=["page"])


@functools.cache
def _client_source() -> str:
    return resources.files("cornea.core").joinpath("client.js").read_text(encoding="utf-8")


@router.get(CLIENT_PATH, include_in_schema=False)
def client(request: Request) -> Response:
    """The JavaScript helper, with the API prefix filled in."""
    prefix = request.app.state.security.api_prefix
    source = _client_source().replace("__API_PREFIX__", prefix)
    return Response(source, media_type="text/javascript")


def _without_query(address: object) -> str:
    """An address without its query or fragment: the start-up link carries a token there."""
    if not isinstance(address, str):
        return "?"
    parts = urlsplit(address)
    return f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.scheme else parts.path or address


@router.post(REPORT_PATH, include_in_schema=False, status_code=204)
async def csp_report(request: Request) -> Response:
    """Log what the content security policy blocked, so a first-run problem can be read.

    The browser sends this by itself, so the body is untrusted: it is size-limited, parsed
    defensively and only ever logged at ``debug``, without any query string.
    """
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_REPORT_BYTES:
        return Response(status_code=204)
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_REPORT_BYTES:
            return Response(status_code=204)
    if body:
        try:
            report = json.loads(body).get("csp-report", {})
        except (ValueError, AttributeError):
            report = {}
        if isinstance(report, dict) and report and logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Blocked by the content security policy: %s (blocked: %s, on page %s, at %s:%s)",
                str(report.get("effective-directive") or report.get("violated-directive"))[:80],
                _without_query(report.get("blocked-uri")),
                _without_query(report.get("document-uri")),
                _without_query(report.get("source-file")),
                str(report.get("line-number", "?"))[:10],
            )
    return Response(status_code=204)
