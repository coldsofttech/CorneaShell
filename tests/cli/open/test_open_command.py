from pathlib import Path

import pytest

from cli_support import Calls, invoke, option_names
from cornea import (
    DEV_CSP,
    Asgi,
    Bridge,
    Process,
    Security,
    Server,
    Static,
    Url,
    Window,
    Wsgi,
)

pytestmark = pytest.mark.usefixtures("restore_cornea_logging")


def test_open_with_a_folder_shows_a_window(calls: Calls) -> None:
    result = invoke("open", "web/dist")

    assert result.exit_code == 0
    assert calls.last["source"] == Static(path=Path("web/dist"))
    assert calls.last["window"] == Window()
    assert calls.last["server"] == Server()
    assert calls.last["security"] == Security()
    assert calls.last["bridge"] == Bridge()
    assert calls.last["on_ready"] is None


def test_open_with_no_source_uses_the_default_lookup(calls: Calls) -> None:
    invoke("open")

    assert calls.last["source"] == Static()


def test_open_maps_every_window_flag(calls: Calls) -> None:
    invoke(
        "open",
        "web/dist",
        "--title",
        "My App",
        "--size",
        "1200x800",
        "--min-size",
        "300x200",
        "--position",
        "-100,50",
        "--frameless",
        "--no-resizable",
        "--on-top",
        "--context-menu",
        "--devtools",
        "--debug",
    )

    assert calls.last["window"] == Window(
        title="My App",
        size=(1200, 800),
        min_size=(300, 200),
        position=(-100, 50),
        frameless=True,
        resizable=False,
        on_top=True,
        context_menu=True,
        devtools=True,
        debug=True,
    )


def test_open_maps_server_security_and_bridge_flags(calls: Calls) -> None:
    invoke(
        "open",
        "web/dist",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
        "--allowed-host",
        "app.local:8765",
        "--allowed-host",
        "other.local",
        "--csp",
        "default-src 'self'",
        "--api-prefix",
        "/v1",
        "--token-ttl",
        "120",
        "--cookie-samesite",
        "lax",
        "--public-path",
        "/health",
        "--public-path",
        "/status",
        "--no-require-origin",
        "--disable-action",
        "open_external",
        "--disable-action",
        "save_file",
    )

    assert calls.last["server"] == Server(host="127.0.0.1", port=8765)
    assert calls.last["security"] == Security(
        allowed_hosts=("app.local:8765", "other.local"),
        csp="default-src 'self'",
        api_prefix="/v1",
        token_ttl=120,
        cookie_samesite="lax",
        public_paths=("/health", "/status"),
        require_origin=False,
    )
    assert calls.last["bridge"] == Bridge(disabled=("open_external", "save_file"))


def test_open_maps_the_bundle_flags(calls: Calls) -> None:
    invoke(
        "open",
        "--package",
        "shipped_ui",
        "--package-path",
        "frontend",
        "--no-spa",
        "--hashed-prefix",
        "static/",
        "--hashed-prefix",
        "fonts/",
    )

    assert calls.last["source"] == Static(
        package="shipped_ui",
        package_path="frontend",
        spa=False,
        hashed_prefixes=("static/", "fonts/"),
    )


def test_open_with_an_address_opens_it_directly(calls: Calls) -> None:
    invoke("open", "http://localhost:5173")
    assert calls.last["source"] == Url("http://localhost:5173")

    invoke("open", "--url", "https://example.com")
    assert calls.last["source"] == Url("https://example.com")


def test_an_address_can_be_proxied(calls: Calls) -> None:
    invoke("open", "http://localhost:5173", "--mode", "proxy")
    assert calls.last["source"] == Url("http://localhost:5173", mode="proxy")

    invoke("open", "--url", "http://localhost:5173", "--mode", "direct")
    assert calls.last["source"] == Url("http://localhost:5173", mode="direct")


def test_a_proxied_address_may_be_frameless(calls: Calls) -> None:
    result = invoke("open", "http://localhost:5173", "--mode", "proxy", "--frameless")

    assert result.exit_code == 0
    assert calls.last["window"] == Window(frameless=True)


def test_a_command_can_be_started_for_the_address(calls: Calls) -> None:
    invoke("open", "--run", "npm run dev", "--url", "http://localhost:5173")
    assert calls.last["source"] == Process("npm run dev", url="http://localhost:5173")

    invoke(
        "open",
        "http://localhost:5173",
        "--run",
        "npm run dev",
        "--run-cwd",
        "web",
        "--run-timeout",
        "90",
        "--mode",
        "proxy",
    )
    assert calls.last["source"] == Process(
        "npm run dev", url="http://localhost:5173", cwd=Path("web"), timeout=90, mode="proxy"
    )


def test_the_dev_csp_profile_is_opt_in(calls: Calls) -> None:
    invoke("open", "web/dist")
    assert calls.last["security"].csp == Security().csp

    invoke("open", "web/dist", "--csp-profile", "dev")
    assert calls.last["security"].csp == DEV_CSP

    invoke("open", "web/dist", "--csp-profile", "strict")
    assert calls.last["security"].csp == Security().csp


def test_the_csp_profile_has_a_flag() -> None:
    assert "--csp-profile" in option_names("open")
    assert "--csp-profile" in option_names("serve")


def test_open_with_apps(calls: Calls) -> None:
    invoke("open", "--asgi", "proj.asgi:application", "--app-dir", "src")
    assert calls.last["source"] == Asgi("proj.asgi:application", app_dir=Path("src"))

    invoke("open", "--wsgi", "app:app")
    assert calls.last["source"] == Wsgi("app:app")


def test_open_with_web_dist_flag(calls: Calls) -> None:
    invoke("open", "--web-dist", "build")

    assert calls.last["source"] == Static(path=Path("build"))


def test_open_shows_what_it_will_do(calls: Calls) -> None:
    result = invoke("open", "web/dist", "--title", "Notes", "--frameless", "--app-id", "a.b")

    assert result.exit_code == 0
    assert "cornea open" in result.stderr
    assert "folder web" in result.stderr
    assert "'Notes', frameless" in result.stderr
    assert "a.b" in result.stderr
