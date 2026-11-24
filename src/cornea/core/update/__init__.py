"""Auto-update: check a source, download, verify, and restart into the new version."""

from cornea.core.update.release import Release, UpdateError
from cornea.core.update.sources import Custom, GitHubRelease, JsonFeed, UpdateSource
from cornea.core.update.updater import Updater
from cornea.core.update.version import is_newer, parse_version

__all__ = [
    "Custom",
    "GitHubRelease",
    "JsonFeed",
    "Release",
    "UpdateError",
    "UpdateSource",
    "Updater",
    "is_newer",
    "parse_version",
]
