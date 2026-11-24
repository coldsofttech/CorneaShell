"""Where updates come from: a JSON feed, GitHub releases, or your own function."""

import fnmatch
import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote

from cornea.core.update.http import get_json, get_text
from cornea.core.update.release import Release, UpdateError, check_address

GITHUB_API = "https://api.github.com"
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@runtime_checkable
class UpdateSource(Protocol):
    """Anything that can say what the newest release is. Implement ``latest`` for your own."""

    def latest(self) -> Release | None:
        """The newest release, or ``None`` when there is nothing to offer."""
        ...


class JsonFeed:
    """A JSON document at an ``https`` address that describes the newest release.

    The document is one object: ``version`` and ``url`` are needed; ``sha256``, ``signature``,
    ``notes``, ``size`` and ``min_version`` are optional. A relative ``url`` is resolved against
    the feed's own address. A feed can be a static file on any web host.

    Example:
        >>> feed = JsonFeed("https://example.com/myapp/latest.json")
        >>> feed.url
        'https://example.com/myapp/latest.json'
    """

    def __init__(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.url = check_address(url, "feed address")
        self.headers = dict(headers or {})
        self.timeout = timeout

    def latest(self) -> Release | None:
        data = get_json(self.url, self.headers, self.timeout)
        try:
            return Release.from_mapping(data, self.url)
        except ValueError as exc:
            raise UpdateError(f"the update feed is not usable: {exc}", "check") from exc

    def __repr__(self) -> str:
        return f"JsonFeed({self.url!r})"


class GitHubRelease:
    """The newest release of a GitHub repository, with the asset that matches ``asset``.

    ``asset`` is a file-name pattern such as ``MyApp-*-win64.zip``; exactly one asset must match.
    The checksum is taken from the asset's GitHub digest, or from a ``<name>.sha256`` asset next
    to it; a ``<name>.sig`` asset is the signature for the signed-update mode. Drafts are never
    offered, and pre-releases only with ``prerelease=True``. A ``token`` only raises GitHub's
    rate limit for the check; downloads use the public asset address.

    Example:
        >>> GitHubRelease("coldsofttech/CorneaShell", asset="*.zip").repo
        'coldsofttech/CorneaShell'
    """

    def __init__(
        self,
        repo: str,
        *,
        asset: str,
        prerelease: bool = False,
        token: str | None = None,
        api_url: str = GITHUB_API,
        timeout: float = 15.0,
    ) -> None:
        if not REPO.match(repo):
            raise ValueError(f"repo looks like 'owner/name', got {repo!r}")
        if not asset.strip():
            raise ValueError("asset must not be empty")
        self.repo = repo
        self.asset = asset
        self.prerelease = prerelease
        self.api_url = check_address(api_url, "api_url").rstrip("/")
        self.timeout = timeout
        self._headers = {"Accept": "application/vnd.github+json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def latest(self) -> Release | None:
        base = f"{self.api_url}/repos/{quote(self.repo)}/releases"
        if self.prerelease:
            listing = get_json(f"{base}?per_page=10", self._headers, self.timeout)
            if not isinstance(listing, list):
                raise UpdateError("GitHub's answer was not a list of releases", "check")
            releases = [r for r in listing if isinstance(r, dict) and not r.get("draft")]
            if not releases:
                return None
            data: Any = releases[0]
        else:
            data = get_json(f"{base}/latest", self._headers, self.timeout)
        return self._release(data)

    def _release(self, data: Any) -> Release:
        if not isinstance(data, dict) or not isinstance(data.get("tag_name"), str):
            raise UpdateError("GitHub's answer was not a release", "check")
        assets = [a for a in data.get("assets") or [] if isinstance(a, dict)]
        by_name: dict[str, dict[str, Any]] = {
            a["name"]: a for a in assets if isinstance(a.get("name"), str)
        }
        matches = [name for name in by_name if fnmatch.fnmatchcase(name, self.asset)]
        if not matches:
            raise UpdateError(f"the release has no file matching {self.asset!r}", "check")
        if len(matches) > 1:
            raise UpdateError(
                f"{self.asset!r} matches more than one file: {sorted(matches)}", "check"
            )
        name = matches[0]
        chosen = by_name[name]
        try:
            return Release(
                version=data["tag_name"],
                url=str(chosen.get("browser_download_url")),
                sha256=self._checksum(chosen, by_name.get(f"{name}.sha256")),
                signature=self._signature(by_name.get(f"{name}.sig")),
                notes=data.get("body") if isinstance(data.get("body"), str) else None,
                size=chosen.get("size") if isinstance(chosen.get("size"), int) else None,
            )
        except ValueError as exc:
            raise UpdateError(f"the release is not usable: {exc}", "check") from exc

    def _checksum(self, asset: dict[str, Any], sidecar: dict[str, Any] | None) -> str | None:
        digest = asset.get("digest")
        if isinstance(digest, str) and digest.startswith("sha256:"):
            return digest.removeprefix("sha256:")
        if sidecar is not None:
            words = get_text(str(sidecar.get("browser_download_url")), timeout=self.timeout).split()
            return words[0] if words else None
        return None

    def _signature(self, sidecar: dict[str, Any] | None) -> str | None:
        if sidecar is None:
            return None
        return get_text(str(sidecar.get("browser_download_url")), timeout=self.timeout).strip()

    def __repr__(self) -> str:
        return f"GitHubRelease({self.repo!r}, asset={self.asset!r})"


class Custom:
    """Your own function as the source: return a :class:`Release`, a feed-style dict, or ``None``.

    Use it for an internal API, a file share or anything else that can tell the version and
    where the file is.

    Example:
        >>> source = Custom(lambda: {"version": "2.0", "url": "https://example.com/app.zip"})
        >>> source.latest().version
        '2.0'
    """

    def __init__(self, function: Callable[[], Release | Mapping[str, Any] | None]) -> None:
        self._function = function

    def latest(self) -> Release | None:
        try:
            result = self._function()
        except UpdateError:
            raise
        except Exception as exc:
            raise UpdateError(f"the update source failed: {exc}", "check") from exc
        if result is None or isinstance(result, Release):
            return result
        try:
            return Release.from_mapping(dict(result))
        except (ValueError, TypeError) as exc:
            raise UpdateError(
                f"the update source returned something unusable: {exc}", "check"
            ) from exc

    def __repr__(self) -> str:
        return f"Custom({getattr(self._function, '__name__', 'function')})"
