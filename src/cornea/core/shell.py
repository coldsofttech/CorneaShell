"""The shell: runs the secured local server that hosts the web UI."""

import os
import socket
import threading
import time
from collections.abc import Iterable
from dataclasses import replace
from types import ModuleType, TracebackType
from typing import Self

import uvicorn
from fastapi import APIRouter, FastAPI

from cornea.core.app import allow_host, create_app
from cornea.core.config import Security, Server, Window
from cornea.core.sources import Url, WebSource, coerce_source
from cornea.core.window import (
    create_native_window,
    load_webview,
    require_webview2,
    require_windows,
    show_window,
)

DEFAULT_WINDOW = Window()
START_TIMEOUT = 10.0
STOP_TIMEOUT = 10.0


def _host_header(host: str, port: int) -> str:
    """``host:port`` as a browser sends it; IPv6 addresses go in brackets."""
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


class Shell:
    """Runs the web UI on a secured local server.

    The server listens on the loopback address by default and picks a free port. The first URL,
    :attr:`url`, carries a one-time token that is exchanged for a session cookie. With a
    ``window``, :meth:`run` opens a native window on that URL (Windows only, and on the main
    thread) and stops the server when the window closes. With ``window=None`` it only serves.

    A direct :class:`~cornea.core.sources.Url` source is different: the window opens that address
    itself and no server is started, so it needs a window with the native frame (the page cannot
    reach the window controls) and :attr:`url` is the address you gave.

    Example:
        >>> with Shell(window=None) as shell:
        ...     shell.url.startswith("http://127.0.0.1:")
        True
    """

    def __init__(
        self,
        source: WebSource | str | os.PathLike[str] | None = None,
        *,
        routers: Iterable[APIRouter] = (),
        security: Security | None = None,
        server: Server | None = None,
        window: Window | None = DEFAULT_WINDOW,
    ) -> None:
        self.security = security or Security()
        self.server = server or Server()
        self.window = window
        web_source = coerce_source(source) if source is not None else None
        self._direct_url: str | None = web_source.url if isinstance(web_source, Url) else None
        if self._direct_url is not None:
            self._check_direct_window(window)
        self.app: FastAPI = create_app(web_source, routers=routers, security=self.security)
        self._socket: socket.socket | None = None
        self._uvicorn: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None
        self._window_error: BaseException | None = None

    # ----- what the server is ---------------------------------------------------------------

    @property
    def running(self) -> bool:
        """Whether the server is accepting requests."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def port(self) -> int:
        """The port the server is bound to. Available after :meth:`start`."""
        self._require_server()
        if self._socket is None:
            raise RuntimeError("the server has not been started")
        return int(self._socket.getsockname()[1])

    @property
    def base_url(self) -> str:
        """The server's address without the token."""
        return f"http://{_host_header(self.server.host, self.port)}"

    @property
    def url(self) -> str:
        """The first URL to open: with a token for the local server, or the direct address."""
        if self._direct_url is not None:
            return self._direct_url
        return f"{self.base_url}/?t={self.app.state.bootstrap_token}"

    # ----- lifecycle ------------------------------------------------------------------------

    def start(self) -> Self:
        """Bind the port and start serving in a background thread."""
        self._require_server()
        if self._thread is not None:
            raise RuntimeError("the server was already started")
        family = socket.AF_INET6 if ":" in self.server.host else socket.AF_INET
        listener = socket.create_server((self.server.host, self.server.port), family=family)
        self._socket = listener
        allow_host(self.app, _host_header(self.server.host, self.port))
        # No access log: it would print the one-time token from the first URL.
        config = uvicorn.Config(self.app, log_level="warning", access_log=False)
        self._uvicorn = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._serve, args=(self._uvicorn, listener), name="cornea-server", daemon=True
        )
        self._thread.start()
        self._wait_until_started()
        return self

    def stop(self) -> None:
        """Stop serving and release the port. Safe to call more than once."""
        server, thread, listener = self._uvicorn, self._thread, self._socket
        if server is not None and thread is not None and thread.is_alive():
            server.should_exit = True
            thread.join(STOP_TIMEOUT)
            if thread.is_alive():
                server.force_exit = True
                thread.join(STOP_TIMEOUT)
        if listener is not None:
            listener.close()

    def run(self) -> None:
        """Show the window and wait until it closes, or just serve when there is no window.

        Serving ends on Ctrl+C or :meth:`stop`. The server is stopped in every case.
        """
        webview = None
        if self.window is not None:
            # Check first, so nothing is started on a machine that cannot show a window.
            require_windows()
            require_webview2()
            webview = load_webview()
        if self._direct_url is None:
            self.start()
        try:
            if webview is not None and self.window is not None:
                self._show_window(webview, self.window)
            else:
                self._serve_until_stopped()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
        if self._window_error is not None:
            raise RuntimeError("the window could not be set up") from self._window_error

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()

    # ----- internals ------------------------------------------------------------------------

    def _require_server(self) -> None:
        if self._direct_url is not None:
            raise RuntimeError("a direct URL has no local server")

    @staticmethod
    def _check_direct_window(window: Window | None) -> None:
        if window is None:
            raise ValueError("a direct URL needs a window; there is nothing to serve without one")
        if window.frameless:
            raise ValueError(
                "a direct URL cannot use a frameless window: the page cannot reach the window "
                "controls. Use the native frame, or the proxy mode when it is available."
            )

    def _serve_until_stopped(self) -> None:
        # A timeout keeps Ctrl+C responsive on Windows, where a plain join() ignores it.
        while self._thread is not None and self._thread.is_alive():
            self._thread.join(0.2)

    def _show_window(self, webview: ModuleType, settings: Window) -> None:
        _, controller = create_native_window(webview, self.url, settings, self._set_window_error)
        self.app.state.window = controller
        show_window(webview, settings)

    def _set_window_error(self, error: BaseException) -> None:
        self._window_error = error

    def _serve(self, server: uvicorn.Server, listener: socket.socket) -> None:
        try:
            server.run(sockets=[listener])
        except BaseException as exc:
            self._error = exc

    def _wait_until_started(self) -> None:
        server, thread = self._uvicorn, self._thread
        assert server is not None  # noqa: S101
        assert thread is not None  # noqa: S101
        deadline = time.monotonic() + START_TIMEOUT
        while not server.started:
            if not thread.is_alive():
                self.stop()
                raise RuntimeError("the server stopped while starting") from self._error
            if time.monotonic() > deadline:
                self.stop()
                raise TimeoutError(f"the server did not start within {START_TIMEOUT:.0f} seconds")
            time.sleep(0.01)


def run(
    source: WebSource | str | os.PathLike[str] | None = None,
    *,
    routers: Iterable[APIRouter] = (),
    security: Security | None = None,
    server: Server | None = None,
    window: Window | None = DEFAULT_WINDOW,
    title: str | None = None,
    debug: bool | None = None,
) -> None:
    """Show the web UI: build a :class:`Shell` and run it until it is closed.

    ``title`` and ``debug`` are shorthands for the same ``window`` settings.
    """
    if window is None:
        if title is not None or debug is not None:
            raise ValueError("title and debug need a window; pass window=Window(...)")
    else:
        window = replace(
            window,
            title=window.title if title is None else title,
            debug=window.debug if debug is None else debug,
        )
    Shell(source, routers=routers, security=security, server=server, window=window).run()
