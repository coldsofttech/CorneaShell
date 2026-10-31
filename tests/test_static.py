import sys
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount

from asgi_client import AsgiClient
from cornea import Static, create_app
from cornea.core.app import allow_host
from cornea.core.static import HASHED_CACHE, REVALIDATE, BundleFiles


def files_client(directory: str, **options: Any) -> AsgiClient:
    """Serve a bundle the way the app does: inside Starlette, which turns errors into responses."""
    return AsgiClient(Starlette(routes=[Mount("/", BundleFiles(directory, **options))]))


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    """A built bundle next to a file outside it that must never be served."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>index</html>", encoding="utf-8")
    (dist / "favicon.ico").write_bytes(b"icon")
    (dist / "assets" / "app.abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "assets" / "app.abc123.css").write_text("body{}", encoding="utf-8")
    (dist / "data.json").write_text("{}", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    return dist


@pytest.fixture
def client(bundle: Path) -> AsgiClient:
    return files_client(str(bundle))


# ----- pages and the fallback -----------------------------------------------------------------


def test_root_serves_index_without_caching(client: AsgiClient) -> None:
    response = client.request("/")

    assert response.status == 200
    assert response.body == b"<html>index</html>"
    assert response.header("content-type") == "text/html; charset=utf-8"
    assert response.header("cache-control") == REVALIDATE


def test_page_routes_fall_back_to_index(client: AsgiClient) -> None:
    for path in ("/dashboard", "/settings/profile", "/a/b/c"):
        response = client.request(path)

        assert response.status == 200
        assert response.body == b"<html>index</html>"
        assert response.header("cache-control") == REVALIDATE


def test_missing_files_are_404_not_index(client: AsgiClient) -> None:
    assert client.request("/missing.js").status == 404
    assert client.request("/assets/missing.css").status == 404
    assert client.request("/dir/missing.png").status == 404


def test_fallback_can_be_turned_off(bundle: Path) -> None:
    client = files_client(str(bundle), spa=False)

    assert client.request("/dashboard").status == 404
    assert client.request("/").status == 200


def test_fallback_only_for_reads(client: AsgiClient) -> None:
    assert client.request("/dashboard", method="POST").status == 405
    assert client.request("/dashboard", method="HEAD").body == b""


# ----- caching and content types --------------------------------------------------------------


def test_fingerprinted_assets_are_cached_for_a_year(client: AsgiClient) -> None:
    response = client.request("/assets/app.abc123.js")

    assert response.status == 200
    assert response.header("cache-control") == HASHED_CACHE
    assert "immutable" in HASHED_CACHE


def test_other_files_are_revalidated(client: AsgiClient) -> None:
    assert client.request("/favicon.ico").header("cache-control") == REVALIDATE
    assert client.request("/data.json").header("cache-control") == REVALIDATE


def test_hashed_prefixes_are_configurable(bundle: Path) -> None:
    client = files_client(str(bundle), hashed_prefixes=("data.json",))

    assert client.request("/assets/app.abc123.js").header("cache-control") == REVALIDATE
    assert client.request("/data.json").header("cache-control") == HASHED_CACHE


@pytest.mark.parametrize(
    ("path", "media_type"),
    [
        ("/assets/app.abc123.js", "text/javascript; charset=utf-8"),
        ("/assets/app.abc123.css", "text/css; charset=utf-8"),
        ("/data.json", "application/json"),
        ("/", "text/html; charset=utf-8"),
    ],
)
def test_content_types_do_not_depend_on_the_system(
    path: str, media_type: str, client: AsgiClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A registry that calls everything text/plain, as some Windows machines do.
    monkeypatch.setattr("mimetypes.guess_type", lambda *args, **kwargs: ("text/plain", None))

    assert client.request(path).header("content-type") == media_type


def test_etag_gives_304(client: AsgiClient) -> None:
    first = client.request("/assets/app.abc123.js")
    etag = first.header("etag")
    assert etag

    again = client.request("/assets/app.abc123.js", headers={"If-None-Match": etag})

    assert again.status == 304


# ----- path traversal -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/../secret.txt",
        "/assets/../../secret.txt",
        "/%2e%2e/secret.txt",
        "/..%2fsecret.txt",
        "/assets/..%2f..%2fsecret.txt",
        "//secret.txt",
        "/..\\secret.txt",
    ],
)
def test_paths_outside_the_bundle_are_never_served(path: str, client: AsgiClient) -> None:
    response = client.request(path)

    assert b"secret" not in response.body
    assert response.status in {200, 404}
    if response.status == 200:
        assert response.body == b"<html>index</html>"


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need extra rights on Windows")
def test_symlinks_out_of_the_bundle_are_not_followed(bundle: Path, tmp_path: Path) -> None:
    (bundle / "link.txt").symlink_to(tmp_path / "secret.txt")

    response = files_client(str(bundle)).request("/link.txt")

    assert b"secret" not in response.body


# ----- lookup order ---------------------------------------------------------------------------


def make_bundle(folder: Path, text: str) -> Path:
    folder.mkdir(parents=True)
    (folder / "index.html").write_text(text, encoding="utf-8")
    return folder


def test_explicit_path_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    explicit = make_bundle(tmp_path / "explicit", "explicit")
    make_bundle(tmp_path / "web" / "dist", "checkout")
    monkeypatch.chdir(tmp_path)

    assert Static(explicit).resolve() == explicit.resolve()


def test_explicit_path_is_not_replaced_when_wrong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_bundle(tmp_path / "web" / "dist", "checkout")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="folder not found"):
        Static(tmp_path / "typo").resolve()


def test_packaged_bundle_is_next(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    packaged = make_bundle(tmp_path / "libs" / "shipped_ui" / "web" / "dist", "packaged")
    (packaged.parent.parent / "__init__.py").write_text("", encoding="utf-8")
    make_bundle(tmp_path / "web" / "dist", "checkout")
    monkeypatch.syspath_prepend(str(tmp_path / "libs"))
    monkeypatch.chdir(tmp_path)

    assert Static(package="shipped_ui").resolve() == packaged.resolve()


def test_custom_folder_inside_the_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ui = make_bundle(tmp_path / "libs" / "shipped_ui2" / "frontend", "packaged")
    (ui.parent / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path / "libs"))

    assert Static(package="shipped_ui2", package_path="frontend").resolve() == ui.resolve()


def test_checkout_bundle_is_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = make_bundle(tmp_path / "web" / "dist", "checkout")
    monkeypatch.chdir(tmp_path)

    assert Static().resolve() == checkout.resolve()
    assert Static(package="not_installed_anywhere").resolve() == checkout.resolve()


def test_nothing_found_lists_the_places_tried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match=r"looked in: .*dist"):
        Static().resolve()


def test_static_settings_are_validated() -> None:
    with pytest.raises(ValueError, match="package_path"):
        Static(package="x", package_path="../escape")
    with pytest.raises(ValueError, match="hashed_prefixes"):
        Static(hashed_prefixes=("assets",))
    with pytest.raises(ValueError, match="hashed_prefixes"):
        Static(hashed_prefixes=("/assets/",))


# ----- through the app ------------------------------------------------------------------------


def sign_in(client: AsgiClient, token: str) -> str:
    response = client.request("/", query=f"t={token}")
    return (response.header("set-cookie") or "").split(";")[0]


def test_app_serves_the_bundle_behind_the_session(bundle: Path) -> None:
    app = create_app(Static(bundle))
    allow_host(app, "127.0.0.1:8000")
    client = AsgiClient(app)
    assert client.request("/dashboard").status == 401

    cookie = sign_in(client, app.state.bootstrap_token)

    page = client.request("/dashboard", cookie=cookie)
    asset = client.request("/assets/app.abc123.js", cookie=cookie)
    assert page.body == b"<html>index</html>"
    assert asset.header("cache-control") == HASHED_CACHE
    assert page.header("content-security-policy") is not None


def test_app_respects_the_spa_setting(bundle: Path) -> None:
    app = create_app(Static(bundle, spa=False))
    allow_host(app, "127.0.0.1:8000")
    client = AsgiClient(app)
    cookie = sign_in(client, app.state.bootstrap_token)

    assert client.request("/dashboard", cookie=cookie).status == 404
