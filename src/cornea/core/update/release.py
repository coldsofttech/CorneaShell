"""What an update source tells the updater: one release, or the reason it could not."""

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


class UpdateError(Exception):
    """An update step failed. The message says which one and is safe to show to a person."""

    def __init__(self, message: str, stage: str = "update") -> None:
        super().__init__(message)
        self.stage = stage
        """``check``, ``download``, ``verify`` or ``install``."""


def check_address(url: str, what: str = "address") -> str:
    """Accept an ``https`` address, or ``http`` only for this machine (tests, local mirrors)."""
    parts = urlsplit(url)
    secure = parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in LOOPBACK)
    if not secure or not parts.hostname or parts.username or parts.password:
        raise ValueError(f"the {what} must be an https address without a login, got {url!r}")
    return url


@dataclass(frozen=True, slots=True)
class Release:
    """One downloadable version, as an update source describes it.

    Example:
        >>> Release("1.4.0", "https://example.com/app-1.4.0.zip").version
        '1.4.0'
    """

    version: str
    """The version this release brings, for example ``1.4.0``."""
    url: str
    """Where the file is. ``https`` only."""
    sha256: str | None = None
    """Hex SHA-256 of the file. The download is refused if it differs."""
    signature: str | None = None
    """Base64 Ed25519 signature of the file's SHA-256 digest, for the signed-update mode."""
    notes: str | None = None
    """Release notes in plain text, for the page to show."""
    size: int | None = None
    """Size of the file in bytes, if the source says. Used for progress."""
    min_version: str | None = None
    """The oldest version that may update straight to this one."""

    def __post_init__(self) -> None:
        from cornea.core.update.version import parse_version

        parse_version(self.version)
        check_address(self.url, "release url")
        if self.sha256 is not None and not SHA256.match(self.sha256):
            raise ValueError("sha256 must be 64 hexadecimal characters")
        if self.min_version is not None:
            parse_version(self.min_version)
        if self.size is not None and self.size < 0:
            raise ValueError("size must not be negative")

    @classmethod
    def from_mapping(cls, data: Any, base_url: str | None = None) -> "Release":
        """Build a release from a feed entry. A relative ``url`` is resolved against ``base_url``.

        Raises:
            ValueError: If a field is missing or has the wrong type.

        Example:
            >>> Release.from_mapping({"version": "2.0", "url": "app.zip"}, "https://a.test/f.json").url
            'https://a.test/app.zip'
        """
        from urllib.parse import urljoin

        if not isinstance(data, dict):
            raise ValueError("the release must be a JSON object")
        version, url = data.get("version"), data.get("url")
        if not isinstance(version, str) or not isinstance(url, str):
            raise ValueError("the release needs a text 'version' and 'url'")
        if base_url is not None:
            url = urljoin(base_url, url)
        fields: dict[str, Any] = {}
        for name in ("sha256", "signature", "notes", "min_version"):
            value = data.get(name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{name} must be text")
            fields[name] = value
        size = data.get("size")
        if size is not None and (not isinstance(size, int) or isinstance(size, bool)):
            raise ValueError("size must be a whole number")
        return cls(version=version, url=url, size=size, **fields)

    def as_dict(self) -> dict[str, Any]:
        """The fields the page may see. The signature and hash are internal."""
        return {
            "version": self.version,
            "notes": self.notes,
            "size": self.size,
            "min_version": self.min_version,
        }
