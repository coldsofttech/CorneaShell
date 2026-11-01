"""The shell: runs the secured local server that hosts the web UI."""

import json
import logging
import os
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType, TracebackType
from typing import Any, Self

import uvicorn
from fastapi import APIRouter, FastAPI

from cornea.core.app.app import AppFactory
from cornea.core.bridge.bridge import ActionRegistry
from cornea.core.config import App, Bridge, Security, Server, Window
from cornea.core.environment import Environment
from cornea.core.logs import Logs
from cornea.core.page.notifications import Notifier
from cornea.core.security.close_guard import CloseGuard
from cornea.core.security.single_instance import AlreadyRunning, InstanceLock, activate_existing
from cornea.core.sources.process import ProcessRunner
from cornea.core.sources.sources import Process, Url, WebSource, coerce_source
from cornea.core.window.window import (
    SimulatedWindow,
    Unavailable,
    check_event_name,
    create_native_window,
    load_webview,
    require_webview2,
    require_windows,
    show_window,
)

DEFAULT_WINDOW = Window()

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Timings:
    """How long start-up took, in seconds since :meth:`Shell.run` (or ``start``) began.

    A value is ``None`` when that step did not happen, for example ``window_shown`` without a
    window.

    Example:
        >>> Timings(server_ready=0.2).page_loaded is None
        True
    """

    process_ready: float | None = None
    """The command of a ``Process`` source answers."""
    server_ready: float | None = None
    """Cornea's own server accepts requests."""
    window_shown: float | None = None
    """The native window appears."""
    page_loaded: float | None = None
    """The first page has loaded in the window."""

    def as_dict(self) -> dict[str, float | None]:
        """The steps by name, for JSON.

        Example:
            >>> Timings(server_ready=0.2).as_dict()["server_ready"]
            0.2
        """
        return {
            "process_ready": self.process_ready,
            "server_ready": self.server_ready,
            "window_shown": self.window_shown,
            "page_loaded": self.page_loaded,
        }

    def summary(self) -> str:
        """One line with the steps that happened.

        Example:
            >>> Timings(server_ready=0.2, page_loaded=0.75).summary()
            'Start-up: server_ready 0.20 s, page_loaded 0.75 s'
        """
        steps = [f"{name} {value:.2f} s" for name, value in self.as_dict().items() if value]
        return "Start-up: " + (", ".join(steps) if steps else "nothing finished")


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
    thread) and stops the server when the window closes. With ``window=None`` it only serves, and
    the window routes answer from a :class:`~cornea.core.window.SimulatedWindow`, so the page can
    be tried in a normal browser.

    A direct :class:`~cornea.core.sources.Url` source is different: the window opens that address
    itself and no server is started, so it needs a window with the native frame (the page cannot
    reach the window controls) and :attr:`url` is the address you gave.

    With ``measure=True`` the start-up time is printed on stderr (and logged) once the first
    page has loaded, or once the server answers when there is no window. Pass a function instead
    to receive the :class:`Timings` yourself. :attr:`timings` has the numbers in either case.

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
        bridge: Bridge | None = None,
        identity: App | None = None,
        measure: bool | Callable[[Timings], None] = False,
    ) -> None:
        self.security = security or Security()
        self.identity = identity or App()
        if window is None and (self.identity.single_instance or self.identity.remember_window):
            raise ValueError("single_instance and remember_window need a window")
        self._lock: InstanceLock | None = None
        self._measure = measure
        self._reported = False
        self._started_at: float | None = None
        self._marks: dict[str, float] = {}
        self.server = server or Server()
        self.window = window
        web_source = coerce_source(source) if source is not None else None
        self._runner: ProcessRunner | None = None
        if isinstance(web_source, Process):
            # The command is started by this shell; the app only sees the address it serves on.
            self._runner = ProcessRunner(web_source)
            web_source = Url(web_source.url, mode=web_source.mode)
        self._direct_url: str | None = None
        if isinstance(web_source, Url) and web_source.mode == "direct":
            self._direct_url = web_source.url
        if self._direct_url is not None:
            self._check_direct_window(window)
        self.app: FastAPI = AppFactory.create(
            web_source, routers=routers, security=self.security, bridge=bridge
        )
        self._guard: CloseGuard = self.app.state.close_guard
        if window is None:
            self.app.state.window = SimulatedWindow(DEFAULT_WINDOW.title)
        self._socket: socket.socket | None = None
        self._uvicorn: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None
        self._window_error: BaseException | None = None

    # ----- what the server is ---------------------------------------------------------------

    @property
    def timings(self) -> Timings:
        """How long start-up took so far. See :class:`Timings`."""
        return Timings(**self._marks)

    def _mark(self, step: str) -> None:
        """Record when a start-up step finished. Only the first time counts."""
        if self._started_at is not None and step not in self._marks:
            self._marks[step] = time.perf_counter() - self._started_at
            logger.debug("Start-up step %s reached after %.3f s", step, self._marks[step])
            if step == ("page_loaded" if self.window is not None else "server_ready"):
                self._report_timings()

    def _log_environment(self) -> None:
        """Write the versions and settings to the top of a debug log. No secrets are in them."""
        for name, value in Environment.details().items():
            logger.debug("%s: %s", name, value)
        logger.debug("Window: %r", self.window)
        logger.debug("Server: %r", self.server)
        logger.debug("Security: %r", self.security)
        logger.debug("App: %r", self.identity)

    def _report_timings(self) -> None:
        """Report the timings once, if asked: the last step has finished, or the run ended."""
        if not self._measure or self._reported:
            return
        self._reported = True
        timings = self.timings
        if callable(self._measure):
            self._measure(timings)
            return
        logger.info(timings.summary())
        print(timings.summary(), file=sys.stderr)  # noqa: T201 - the point of measure=True

    @property
    def actions(self) -> ActionRegistry:
        """The native actions the page can call. Register your own with :meth:`action`."""
        registry: ActionRegistry = self.app.state.actions
        return registry

    def action(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a function as a native action: ``@shell.action("pick_report")``.

        The page calls it with ``POST {api_prefix}/bridge/pick_report`` and a JSON body of named
        arguments; the return value comes back as ``{"available": true, "result": ...}``. From
        the page, ``cornea.call("pick_report", {...})`` does the same (see ``/api/client.js``).
        Actions are Python code, so the command line cannot register them.

        Raises:
            ValueError: If the name is not lowercase words joined by underscores, is a built-in
                action, or is already registered.

        Example:
            >>> shell = Shell(window=None)
            >>> @shell.action("shout")
            ... def shout(text: str) -> str:
            ...     return text.upper()
            >>> "shout" in shell.actions.names()
            True
        """
        return self.actions.action(name)

    def close_guard(self, function: Callable[[], bool]) -> Callable[[], bool]:
        """Hold the window open while ``function()`` returns true: ``@shell.close_guard``.

        It is asked whenever the window is about to close, by the close button, Alt+F4 or the
        taskbar. When it holds, the window stays and the page gets a ``cornea:close-blocked``
        event, so it can ask the person. The page then closes with ``force``. A function that
        raises never holds the window.

        Example:
            >>> shell = Shell(window=None)
            >>> export_running = False
            >>> @shell.close_guard
            ... def busy() -> bool:
            ...     return export_running
            >>> busy()
            False
        """
        self._guard.add(function)
        return function

    def notify(self, event: str, detail: Any = None) -> None:
        """Tell the page something happened, as a ``cornea:<event>`` event on its ``window``.

        ``detail`` must be JSON. Without a window this does nothing, and a page that has not
        loaded yet does not hear it.

        Raises:
            ValueError: If the event name is not allowed.

        Example:
            >>> shell = Shell(window=None)
            >>> shell.notify("export-done", {"rows": 3})  # the page hears "cornea:export-done"
        """
        controller = self.app.state.window
        if controller is None:
            check_event_name(event)
            return
        controller.notify(event, detail)

    def show_notification(
        self, title: str, message: str, notification_id: str | None = None
    ) -> None:
        """Show a Windows toast with a plain-text ``title`` and ``message``.

        Windows draws it, so its look and place are Windows'. A click brings the window to the
        front and sends the page a ``cornea:notification-click`` event with ``notification_id``.
        This is always available to your code; ``Bridge(notifications=True)`` is what lets the
        page ask for one.

        Raises:
            ValueError: If the title, message or id is not allowed.
            RuntimeError: If there is no window, or the ``notifications`` extra is missing.

        Example:
            >>> shell = Shell(window=None)
            >>> shell.show_notification("Export finished", "3 files were saved.")
            Traceback (most recent call last):
            ...
            RuntimeError: There is no window to show a notification from.
        """
        Notifier.check(title, message, notification_id)
        try:
            self.app.state.window.show_notification(title, message, notification_id)
        except Unavailable as exc:
            raise RuntimeError(str(exc)) from exc

    @property
    def is_direct(self) -> bool:
        """Whether the window opens a ``Url`` itself, with no local server."""
        return self._direct_url is not None

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
        return f"{self.base_url}/?cornea_token={self.app.state.bootstrap_token}"

    # ----- lifecycle ------------------------------------------------------------------------

    def start(self) -> Self:
        """Bind the port and start serving in a background thread.

        Use it (or ``with Shell(...)``) when you want the server without :meth:`run`, for example
        in a test. Call :meth:`stop` when you are done.

        Example:
            >>> shell = Shell(window=None).start()
            >>> shell.running
            True
            >>> shell.stop()
        """
        self._require_server()
        if self._thread is not None:
            raise RuntimeError("the server was already started")
        if self._started_at is None:
            self._started_at = time.perf_counter()
        self._start_process()
        try:
            return self._start_server()
        except BaseException:
            self.stop()  # do not leave the command running behind a failed start
            raise

    def _start_server(self) -> Self:
        family = socket.AF_INET6 if ":" in self.server.host else socket.AF_INET
        listener = socket.create_server((self.server.host, self.server.port), family=family)
        self._socket = listener
        AppFactory.allow_host(self.app, _host_header(self.server.host, self.port))
        logger.debug("Serving on %s", self.base_url)
        # No access log: it would print the one-time token from the first URL.
        config = uvicorn.Config(self.app, log_level="warning", access_log=False)
        self._uvicorn = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._serve, args=(self._uvicorn, listener), name="cornea-server", daemon=True
        )
        self._thread.start()
        self._wait_until_started()
        self._mark("server_ready")
        return self

    def stop(self) -> None:
        """Stop serving and release the port. Safe to call more than once.

        Example:
            >>> shell = Shell(window=None).start()
            >>> shell.stop()
            >>> shell.running
            False
        """
        server, thread, listener = self._uvicorn, self._thread, self._socket
        if server is not None and thread is not None and thread.is_alive():
            server.should_exit = True
            thread.join(STOP_TIMEOUT)
            if thread.is_alive():
                server.force_exit = True
                thread.join(STOP_TIMEOUT)
        if listener is not None:
            listener.close()
        if self._runner is not None:
            self._runner.stop()
        if self._lock is not None:
            self._lock.release()

    def run(self, on_ready: Callable[["Shell"], None] | None = None) -> None:
        """Show the window and wait until it closes, or just serve when there is no window.

        ``on_ready`` is called with the shell once it is serving, before the window is shown. Use
        it to announce the address, for example with :func:`ready_line`. Serving ends on Ctrl+C
        or :meth:`stop`. The server is stopped in every case.

        Raises:
            RuntimeError: If the window could not be set up, or WebView2 or pywebview is missing.

        Example:
            >>> shell = Shell(Static("web/dist"), window=Window(title="My App"))  # doctest: +SKIP
            >>> shell.run()  # opens the window; returns when it is closed  # doctest: +SKIP
            >>> shell = Shell(Static("web/dist"), window=None)  # doctest: +SKIP
            >>> shell.run(on_ready=lambda s: print(ready_line(s)))  # doctest: +SKIP
        """
        self._started_at = time.perf_counter()
        if self.window is not None and self.window.debug:
            Logs.enable_debug()
        logger.debug(
            "Starting: %s, %s",
            "direct address" if self._direct_url is not None else "local server",
            "with a window" if self.window is not None else "no window",
        )
        if logger.isEnabledFor(logging.DEBUG):
            self._log_environment()
        webview = None
        if self.window is not None:
            # Check first, so nothing is started on a machine that cannot show a window.
            require_windows()
            require_webview2()
            webview = load_webview()
            self._check_icon(self.window)
            self._take_lock()
        if self._direct_url is None:
            self.start()
        else:
            self._start_process()
        try:
            if on_ready is not None:
                on_ready(self)
            if webview is not None and self.window is not None:
                self._show_window(webview, self.window)
            else:
                self._serve_until_stopped()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
            logger.debug("Stopped")
            self._report_timings()  # a start that never got as far as the last step
        if self._window_error is not None:
            logger.debug("The window could not be set up", exc_info=self._window_error)
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

    @staticmethod
    def _check_icon(window: Window) -> None:
        """Fail before anything starts if the icon file is not there."""
        if window.icon is not None and not Path(window.icon).is_file():
            raise FileNotFoundError(f"window icon not found: {Path(window.icon).resolve()}")

    def _take_lock(self) -> None:
        """Allow one copy of the app at a time, if asked: otherwise wake the first copy."""
        if not self.identity.single_instance or self.identity.id is None:
            return
        lock = InstanceLock(self.identity.id)
        if not lock.acquire():
            raise AlreadyRunning(self.identity.id, activated=activate_existing(self.identity.id))
        self._lock = lock

    def _start_process(self) -> None:
        """Start the command of a ``Process`` source, once, and wait until it answers."""
        if self._runner is not None and self._runner.running:
            return
        if self._runner is not None:
            self._runner.start()
            self._mark("process_ready")

    def _require_server(self) -> None:
        if self._direct_url is not None:
            raise RuntimeError("a direct URL has no local server")

    @staticmethod
    def _check_direct_window(window: Window | None) -> None:
        if window is None:
            raise ValueError("a direct URL needs a window; there is nothing to serve without one")
        if window.frameless and not window.js_api:
            raise ValueError(
                "a direct URL cannot use a frameless window: the page cannot reach the window "
                "controls. Use the native frame, serve the address through the proxy mode, or "
                "set js_api=True to give the page the controls (only for pages you trust)."
            )

    def _serve_until_stopped(self) -> None:
        # A timeout keeps Ctrl+C responsive on Windows, where a plain join() ignores it.
        while self._thread is not None and self._thread.is_alive():
            self._thread.join(0.2)

    def _show_window(self, webview: ModuleType, settings: Window) -> None:
        _, controller = create_native_window(
            webview,
            self.url,
            settings,
            self._set_window_error,
            self.identity,
            self._mark,
            self.actions,
        )
        if self._lock is not None:
            self._lock.serve(controller.activate)
        controller.guard = self._guard
        controller.notifier = Notifier(self.identity.id, settings.title, settings.icon)
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


def ready_line(shell: Shell) -> str:
    """A one-line JSON message that says where the UI is, for tools that start the shell.

    Example:
        >>> with Shell(window=None) as shell:
        ...     json.loads(ready_line(shell))["event"]
        'ready'
    """
    message = {
        "event": "ready",
        "url": shell.url,
        "port": None if shell.is_direct else shell.port,
        "window": shell.window is not None,
    }
    return json.dumps(message)


def run(
    source: WebSource | str | os.PathLike[str] | None = None,
    *,
    routers: Iterable[APIRouter] = (),
    security: Security | None = None,
    server: Server | None = None,
    window: Window | None = DEFAULT_WINDOW,
    bridge: Bridge | None = None,
    identity: App | None = None,
    measure: bool | Callable[[Timings], None] = False,
    title: str | None = None,
    debug: bool | None = None,
    on_ready: Callable[[Shell], None] | None = None,
) -> None:
    """Show the web UI: build a :class:`Shell` and run it until it is closed.

    ``title`` and ``debug`` are shorthands for the same ``window`` settings. ``on_ready`` is
    called once the shell is serving; see :meth:`Shell.run`. ``measure`` reports the start-up
    time: see :class:`Shell`.

    Example:
        >>> run("web/dist", title="My App")  # doctest: +SKIP
        >>> run(Static("web/dist"), window=Window(frameless=True), measure=True)  # doctest: +SKIP
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
    shell = Shell(
        source,
        routers=routers,
        security=security,
        server=server,
        window=window,
        bridge=bridge,
        identity=identity,
        measure=measure,
    )
    shell.run(on_ready=on_ready)
