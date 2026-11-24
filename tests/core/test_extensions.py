"""The hook that lets an optional package add routes and a start page to a shell."""

import http.client
from collections.abc import Iterable
from typing import Any

from fastapi import APIRouter

from cornea import Shell


class Probe:
    """An extension that records how the shell treats it."""

    def __init__(self, path: str = "/", framing: bool = False) -> None:
        self.path = path
        self.allows_framing = framing
        self.bound: Shell | None = None
        self.router = APIRouter()

        @self.router.get("/probe")
        def probe() -> dict[str, str]:
            return {"hello": "world"}

    def routers(self) -> Iterable[APIRouter]:
        return [self.router]

    def start_path(self, api_prefix: str) -> str:
        return self.path.replace("{api}", api_prefix)

    def bind(self, shell: Shell) -> None:
        self.bound = shell


def get(shell: Shell, path: str, cookie: str | None = None) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", shell.port, timeout=5)
    connection.request("GET", path, headers={"Cookie": cookie} if cookie else {})
    response = connection.getresponse()
    result = (response.status, dict(response.getheaders()), response.read())
    connection.close()
    return result


def test_an_extension_is_bound_and_its_routes_are_mounted_under_the_api_prefix() -> None:
    probe = Probe()
    with Shell(window=None, extensions=[probe]) as shell:
        assert probe.bound is shell
        _, headers, _ = get(shell, f"/?cornea_token={shell.app.state.bootstrap_token}")
        cookie = headers["set-cookie"].split(";")[0]
        status, _, body = get(shell, "/api/probe", cookie)
    assert (status, body) == (200, b'{"hello":"world"}')


def test_the_window_opens_on_the_start_path_the_extension_names() -> None:
    with Shell(window=None, extensions=[Probe("{api}/probe-page")]) as shell:
        assert shell.url.startswith(f"{shell.base_url}/api/probe-page?cornea_token=")


def test_a_plain_shell_still_opens_on_the_root() -> None:
    with Shell(window=None, extensions=[Probe()]) as shell:
        assert shell.url.startswith(f"{shell.base_url}/?cornea_token=")


def test_framing_is_allowed_only_when_an_extension_asks_for_it() -> None:
    assert "frame-ancestors 'none'" in Shell(window=None, extensions=[Probe()]).security.csp
    framed = Shell(window=None, extensions=[Probe(framing=True)]).security.csp
    assert "frame-ancestors 'self'" in framed
    assert "frame-ancestors 'none'" not in framed


def test_no_extensions_changes_nothing() -> None:
    shell: Any = Shell(window=None)
    assert shell.extensions == ()
    assert "frame-ancestors 'none'" in shell.security.csp
