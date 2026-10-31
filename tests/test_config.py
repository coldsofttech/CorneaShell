import dataclasses

import pytest

from cornea import DEV_CSP, Security, Server, Window
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
