"""Small, strict HTTP helpers for the updater. They use only the standard library."""

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from cornea.core.update.release import UpdateError, check_address

logger = logging.getLogger(__name__)

USER_AGENT = "CorneaShell-Updater"
MAX_DOCUMENT = 2 * 1024 * 1024
"""The most a feed or a release listing may be, in bytes."""
MAX_DOWNLOAD = 4 * 1024**3
CHUNK = 64 * 1024


def _opener() -> Any:
    """An opener that refuses to be sent from https to a plain http address."""
    import urllib.request

    class Strict(urllib.request.HTTPRedirectHandler):
        def redirect_request(
            self, req: Any, fp: Any, code: Any, msg: Any, headers: Any, newurl: Any
        ) -> Any:
            try:
                check_address(newurl, "redirect")
            except ValueError as exc:
                raise UpdateError(str(exc), "download") from exc
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(Strict)


def _open(url: str, headers: Mapping[str, str] | None, timeout: float) -> Any:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(  # noqa: S310 - the scheme was checked by check_address
        check_address(url), headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    try:
        return _opener().open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"the server answered {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"could not reach the server: {getattr(exc, 'reason', exc)}") from exc


def get_json(url: str, headers: Mapping[str, str] | None = None, timeout: float = 15.0) -> Any:
    """Read a small JSON document. Raises :class:`UpdateError` when it cannot be had or read."""
    with _open(url, headers, timeout) as response:
        body = response.read(MAX_DOCUMENT + 1)
    if len(body) > MAX_DOCUMENT:
        raise UpdateError("the update feed is too large")
    try:
        return json.loads(body)
    except ValueError as exc:
        raise UpdateError("the update feed is not valid JSON") from exc


def get_text(url: str, headers: Mapping[str, str] | None = None, timeout: float = 15.0) -> str:
    """Read a small text file, such as a checksum."""
    with _open(url, headers, timeout) as response:
        body = response.read(MAX_DOCUMENT + 1)
    if len(body) > MAX_DOCUMENT:
        raise UpdateError("the file is too large")
    return str(body.decode("utf-8", errors="replace"))


def download(
    url: str,
    target: Path,
    *,
    expected_size: int | None = None,
    timeout: float = 30.0,
    progress: Callable[[int, int | None], None] | None = None,
    limit: int = MAX_DOWNLOAD,
) -> str:
    """Stream ``url`` into ``target`` and return the file's hex SHA-256.

    The file is written under a temporary name and moved into place only when complete, so a
    partial download is never mistaken for a finished one.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    received = 0
    try:
        with _open(url, None, timeout) as response, partial.open("wb") as out:
            header = response.headers.get("Content-Length")
            total = int(header) if header and header.isdigit() else expected_size
            if total is not None and total > limit:
                raise UpdateError("the update is larger than allowed", "download")
            while chunk := response.read(CHUNK):
                received += len(chunk)
                if received > limit:
                    raise UpdateError("the update is larger than allowed", "download")
                digest.update(chunk)
                out.write(chunk)
                if progress is not None:
                    progress(received, total)
        if total is not None and received != total:
            raise UpdateError("the download ended early", "download")
        if expected_size is not None and received != expected_size:
            raise UpdateError("the download is not the size the release announced", "download")
        partial.replace(target)
    except UpdateError as exc:
        partial.unlink(missing_ok=True)
        exc.stage = "download"
        raise
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"could not save the update: {exc}", "download") from exc
    return digest.hexdigest()
