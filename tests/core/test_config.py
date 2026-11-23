import dataclasses

import pytest

from cornea import DEV_CSP, NONCE_CSP, STYLES_CSP, Security, Server, Window
from cornea.core.config import DEFAULT_CSP


def test_server_defaults_to_loopback_and_free_port() -> None:
    server = Server()

    assert server.host == "127.0.0.1"
    assert server.port == 0


@pytest.mark.parametrize("port", [-1, 65536])
def test_server_rejects_bad_port(port: int) -> None:
    with pytest.raises(ValueError, match="port"):
        Server(port=port)


def test_server_rejects_empty_host() -> None:
    with pytest.raises(ValueError, match="host"):
        Server(host=" ")


def test_security_defaults_are_strict() -> None:
    security = Security()

    assert security.allowed_hosts == ()
    assert security.csp == DEFAULT_CSP
    assert "'unsafe-inline'" not in security.csp
    assert security.api_prefix == "/api"
    assert security.cookie_samesite == "strict"


def test_security_normalizes_allowed_hosts() -> None:
    security = Security(allowed_hosts=(" Example.COM ", "localhost:8000"))

    assert security.allowed_hosts == ("example.com", "localhost:8000")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"allowed_hosts": ("",)},
        {"csp": " "},
        {"api_prefix": "api"},
        {"api_prefix": "/api/"},
        {"api_prefix": "/"},
        {"token_ttl": 0},
    ],
)
def test_security_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - messages differ per field
        Security(**kwargs)  # type: ignore[arg-type]


def test_settings_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        Window().title = "other"  # type: ignore[misc]


def test_window_context_menu_and_devtools_off_by_default() -> None:
    window = Window()

    assert not window.context_menu_enabled
    assert not window.devtools_enabled


def test_window_options_enable_individually() -> None:
    assert Window(context_menu=True).context_menu_enabled
    assert not Window(context_menu=True).devtools_enabled
    assert Window(devtools=True).devtools_enabled
    assert not Window(devtools=True).context_menu_enabled


def test_window_debug_enables_both() -> None:
    window = Window(debug=True)

    assert window.context_menu_enabled
    assert window.devtools_enabled


@pytest.mark.parametrize("field", ["size", "min_size"])
def test_window_rejects_non_positive_size(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        Window(**{field: (0, 100)})  # type: ignore[arg-type]


def test_the_dev_csp_loosens_only_what_dev_servers_need() -> None:
    strict = {part.split()[0]: part for part in DEFAULT_CSP.split("; ")}
    dev = {part.split()[0]: part for part in DEV_CSP.split("; ")}

    loosened = {name for name in strict if strict[name] != dev[name]}
    assert loosened == {"script-src", "style-src"}
    assert set(dev) == set(strict)
    for kept in ("default-src", "object-src", "base-uri", "frame-ancestors", "form-action"):
        assert dev[kept] == strict[kept]


def test_the_dev_csp_is_never_the_default() -> None:
    assert Security().csp == DEFAULT_CSP
    assert Security().csp != DEV_CSP
    assert "'unsafe-inline'" in DEV_CSP
    assert Security(csp=DEV_CSP).csp == DEV_CSP


def _directives(policy: str) -> dict[str, str]:
    return {part.split()[0]: part for part in policy.split("; ")}


def test_the_styles_csp_loosens_style_src_only() -> None:
    strict, styles = _directives(DEFAULT_CSP), _directives(STYLES_CSP)

    assert {name for name in strict if strict[name] != styles[name]} == {"style-src"}
    assert styles["style-src"] == "style-src 'self' 'unsafe-inline'"
    assert styles["script-src"] == "script-src 'self'"


def test_the_nonce_csp_loosens_style_src_only_and_without_unsafe_inline() -> None:
    strict, nonce = _directives(DEFAULT_CSP), _directives(NONCE_CSP)

    assert {name for name in strict if strict[name] != nonce[name]} == {"style-src"}
    assert nonce["style-src"] == "style-src 'self' 'nonce-{nonce}'"
    assert "unsafe-inline" not in NONCE_CSP


def test_the_default_csp_is_exported_from_the_package() -> None:
    import cornea

    assert Security().csp == cornea.DEFAULT_CSP
    assert (cornea.STYLES_CSP, cornea.NONCE_CSP) == (STYLES_CSP, NONCE_CSP)


def test_a_nonce_placeholder_must_be_inside_nonce() -> None:
    with pytest.raises(ValueError, match="nonce-"):
        Security(csp="default-src 'self'; style-src {nonce}")
    assert Security(csp=NONCE_CSP).csp == NONCE_CSP
