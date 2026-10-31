import asyncio
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from cornea import Asgi, Static, Url, WebSource, Wsgi
from cornea.core.sources import coerce_source


@pytest.fixture
def app_dir(tmp_path: Path) -> Iterator[Path]:
    """A folder with importable ASGI and WSGI sample apps, removed from sys.path afterwards."""
    (tmp_path / "sample_apps.py").write_text(
        "async def asgi_app(scope, receive, send):\n"
        "    await send({'type': 'http.response.start', 'status': 200, 'headers': []})\n"
        "    await send({'type': 'http.response.body', 'body': b'asgi'})\n"
        "\n"
        "def wsgi_app(environ, start_response):\n"
        "    start_response('200 OK', [('Content-Type', 'text/plain')])\n"
        "    return [b'wsgi']\n"
        "\n"
        "class Holder:\n"
        "    app = staticmethod(wsgi_app)\n"
        "\n"
        "not_callable = 42\n",
        encoding="utf-8",
    )
    before = list(sys.path)
    yield tmp_path
    sys.path[:] = before
    sys.modules.pop("sample_apps", None)


def _call(app: Callable[..., Any]) -> tuple[int, bytes]:
    """Send one GET request through an ASGI app and return the status and body."""
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 80),
    }
    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body


def test_static_resolves_bundle_folder(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")

    assert Static(tmp_path).resolve() == tmp_path.resolve()
    assert Static(str(tmp_path)).directory == tmp_path


def test_static_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="folder not found"):
        Static(tmp_path / "missing").resolve()


def test_static_missing_index(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"index\.html"):
        Static(tmp_path).resolve()


def test_url_accepts_http_and_https() -> None:
    assert Url("http://localhost:5173").mode == "direct"
    assert Url("https://example.com").url == "https://example.com"


@pytest.mark.parametrize("url", ["localhost:5173", "ftp://example.com", "http://", "web/dist"])
def test_url_rejects_non_http_addresses(url: str) -> None:
    with pytest.raises(ValueError, match="http or https"):
        Url(url)


def test_url_can_be_proxied() -> None:
    assert Url("http://localhost:5173", mode="proxy").mode == "proxy"


def test_url_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="mode must be"):
        Url("http://localhost:5173", mode="other")  # type: ignore[arg-type]


@pytest.mark.parametrize("target", ["module", "module:", ":attr", "a b:c", "mod:attr()"])
def test_import_string_must_be_module_colon_attribute(target: str) -> None:
    with pytest.raises(ValueError, match="module:attribute"):
        Asgi(target)
    with pytest.raises(ValueError, match="module:attribute"):
        Wsgi(target)


def test_target_must_be_string_or_callable() -> None:
    with pytest.raises(TypeError, match="import string or a callable"):
        Asgi(42)  # type: ignore[arg-type]


def test_asgi_loads_from_import_string(app_dir: Path) -> None:
    app = Asgi("sample_apps:asgi_app", app_dir=app_dir).load()

    assert _call(app) == (200, b"asgi")


def test_asgi_accepts_the_app_itself() -> None:
    async def app(scope: Any, receive: Any, send: Any) -> None: ...

    assert Asgi(app).load() is app


def test_asgi_import_errors_are_clear(app_dir: Path) -> None:
    with pytest.raises(ImportError, match="cannot import module"):
        Asgi("no_such_module_xyz:app").load()
    with pytest.raises(ImportError, match="no attribute"):
        Asgi("sample_apps:missing", app_dir=app_dir).load()


def test_asgi_target_must_be_callable(app_dir: Path) -> None:
    with pytest.raises(TypeError, match="not a callable"):
        Asgi("sample_apps:not_callable", app_dir=app_dir).load()


def test_wsgi_is_adapted_to_asgi(app_dir: Path) -> None:
    app = Wsgi("sample_apps:wsgi_app", app_dir=app_dir).load()

    assert _call(app) == (200, b"wsgi")


def test_wsgi_supports_dotted_attributes(app_dir: Path) -> None:
    app = Wsgi("sample_apps:Holder.app", app_dir=app_dir).load()

    assert _call(app) == (200, b"wsgi")


def test_wsgi_target_must_be_callable(app_dir: Path) -> None:
    with pytest.raises(TypeError, match="not a callable"):
        Wsgi("sample_apps:not_callable", app_dir=app_dir).load()


def test_wsgi_without_extra_gives_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "a2wsgi", None)

    with pytest.raises(ImportError, match=r"cornea-shell\[wsgi\]"):
        Wsgi(lambda environ, start_response: []).load()


def test_coerce_passes_sources_through() -> None:
    source = Url("http://localhost:5173")

    assert coerce_source(source) is source


def test_coerce_http_string_is_url() -> None:
    assert coerce_source("HTTPS://example.com") == Url("HTTPS://example.com")


def test_coerce_path_is_static(tmp_path: Path) -> None:
    assert coerce_source("web/dist") == Static(Path("web/dist"))
    assert coerce_source(tmp_path) == Static(tmp_path)


def test_coerce_rejects_other_types() -> None:
    with pytest.raises(TypeError, match="web source, path or URL"):
        coerce_source(42)  # type: ignore[arg-type]


def test_all_sources_share_the_base_class() -> None:
    assert issubclass(Static, WebSource)
    assert issubclass(Url, WebSource)
    assert issubclass(Asgi, WebSource)
    assert issubclass(Wsgi, WebSource)
