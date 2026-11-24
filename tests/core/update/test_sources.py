import pytest

from cornea.core.update import Custom, GitHubRelease, JsonFeed, Release, UpdateError
from update_support import Site


def test_json_feed_reads_a_release(site: Site) -> None:
    url = site.add(
        "/feed.json",
        {"version": "1.4.0", "url": "app.zip", "sha256": "ab" * 32, "notes": "Fixes", "size": 5},
    )
    release = JsonFeed(url).latest()
    assert release == Release(
        "1.4.0", site.base + "/app.zip", sha256="ab" * 32, notes="Fixes", size=5
    )


def test_json_feed_rejects_plain_http_to_other_hosts() -> None:
    with pytest.raises(ValueError, match="https"):
        JsonFeed("http://example.com/feed.json")


def test_json_feed_rejects_a_login_in_the_address() -> None:
    with pytest.raises(ValueError, match="https"):
        JsonFeed("https://user:pass@example.com/feed.json")


def test_json_feed_reports_a_missing_feed(site: Site) -> None:
    with pytest.raises(UpdateError, match="404"):
        JsonFeed(site.base + "/nothing.json").latest()


def test_json_feed_reports_bad_json_and_bad_fields(site: Site) -> None:
    with pytest.raises(UpdateError, match="not valid JSON"):
        JsonFeed(site.add("/bad.json", b"<html>")).latest()
    with pytest.raises(UpdateError, match="not usable"):
        JsonFeed(site.add("/odd.json", {"version": "1.0"})).latest()
    with pytest.raises(UpdateError, match="not usable"):
        JsonFeed(
            site.add("/hash.json", {"version": "1.0", "url": "a.zip", "sha256": "xyz"})
        ).latest()


def test_feed_does_not_follow_a_redirect_to_plain_http(site: Site) -> None:
    with pytest.raises(UpdateError, match="https"):
        JsonFeed(site.base + "/redirect-insecure").latest()


def _github_release(site: Site, **extra: object) -> None:
    site.add(
        "/repos/acme/app/releases/latest",
        {
            "tag_name": "v2.0.0",
            "body": "New things",
            "assets": [
                {
                    "name": "App-2.0.0-win64.zip",
                    "browser_download_url": site.base + "/dl/App-2.0.0-win64.zip",
                    "size": 10,
                    **extra,
                },
                {"name": "App-2.0.0-src.tar.gz", "browser_download_url": site.base + "/dl/src"},
            ],
        },
    )


def test_github_release_picks_the_matching_asset_and_its_digest(site: Site) -> None:
    _github_release(site, digest="sha256:" + "cd" * 32)
    source = GitHubRelease("acme/app", asset="*-win64.zip", api_url=site.base)
    release = source.latest()
    assert release is not None
    assert release.version == "v2.0.0"
    assert release.url.endswith("/dl/App-2.0.0-win64.zip")
    assert release.sha256 == "cd" * 32
    assert release.notes == "New things"
    assert release.size == 10


def test_github_release_reads_sidecar_checksum_and_signature(site: Site) -> None:
    _github_release(site)
    releases = site.routes["/repos/acme/app/releases/latest"]
    import json

    data = json.loads(releases)
    for suffix, route in ((".sha256", "/dl/sum"), (".sig", "/dl/sig")):
        data["assets"].append(
            {"name": "App-2.0.0-win64.zip" + suffix, "browser_download_url": site.base + route}
        )
    site.add("/repos/acme/app/releases/latest", data)
    site.add("/dl/sum", ("ef" * 32 + "  App-2.0.0-win64.zip\n").encode())
    site.add("/dl/sig", b"c2ln\n")
    release = GitHubRelease("acme/app", asset="*-win64.zip", api_url=site.base).latest()
    assert release is not None
    assert release.sha256 == "ef" * 32
    assert release.signature == "c2ln"


def test_github_release_needs_exactly_one_matching_asset(site: Site) -> None:
    _github_release(site)
    with pytest.raises(UpdateError, match="no file matching"):
        GitHubRelease("acme/app", asset="*.msi", api_url=site.base).latest()
    with pytest.raises(UpdateError, match="more than one"):
        GitHubRelease("acme/app", asset="App-*", api_url=site.base).latest()


def test_github_release_prerelease_lists_and_skips_drafts(site: Site) -> None:
    site.add(
        "/repos/acme/app/releases",
        [
            {"tag_name": "v3.0.0-draft", "draft": True, "assets": []},
            {
                "tag_name": "v2.1.0rc1",
                "prerelease": True,
                "assets": [{"name": "a.zip", "browser_download_url": site.base + "/a.zip"}],
            },
        ],
    )
    source = GitHubRelease("acme/app", asset="a.zip", api_url=site.base, prerelease=True)
    release = source.latest()
    assert release is not None
    assert release.version == "v2.1.0rc1"


def test_github_release_validates_the_repo_name() -> None:
    with pytest.raises(ValueError, match="owner/name"):
        GitHubRelease("not-a-repo", asset="*.zip")


def test_custom_accepts_a_release_a_dict_or_nothing() -> None:
    release = Release("1.1", "https://example.com/a.zip")
    assert Custom(lambda: release).latest() is release
    assert Custom(
        lambda: {"version": "1.2", "url": "https://example.com/b.zip"}
    ).latest() == Release("1.2", "https://example.com/b.zip")
    assert Custom(lambda: None).latest() is None


def test_custom_wraps_failures() -> None:
    def boom() -> None:
        raise RuntimeError("db is down")

    with pytest.raises(UpdateError, match="db is down"):
        Custom(boom).latest()
    with pytest.raises(UpdateError, match="unusable"):
        Custom(lambda: {"version": "x"}).latest()
