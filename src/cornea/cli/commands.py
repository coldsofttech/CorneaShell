"""Command line interface built on Typer and Rich. It only parses input and shows output."""

import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table

from cornea import Bridge, Security, Server, Shell, WebSource, Window, __version__, ready_line
from cornea import run as run_shell
from cornea.cli import options, output

EXAMPLES: dict[str, tuple[str, ...]] = {
    "": ("cornea --version", "cornea --quiet info", "cornea --no-color info"),
    "info": ("cornea info", "cornea info --json"),
    "open": (
        "cornea open web/dist",
        'cornea open web/dist --title "My App" --size 1200x800 --frameless --debug',
        "cornea open http://localhost:5173 --size 1280x800",
        "cornea open http://localhost:5173 --mode proxy --csp-profile dev --frameless",
    ),
    "serve": (
        "cornea serve web/dist",
        "cornea serve --asgi myproject.asgi:application --app-dir .",
        "cornea serve web/dist --port 8765 --public-path /health --public-path /status",
        "cornea serve http://localhost:5173 --mode proxy --csp-profile dev",
    ),
}
"""Example invocations by command name (empty for the top level). Tested and used in the docs."""


def _epilog(command: str) -> str:
    """Help footer that lists the examples for ``command``."""
    return "[bold]Examples[/bold]\n\n" + "\n\n".join(f"  $ {line}" for line in EXAMPLES[command])


app = typer.Typer(
    name="cornea",
    help="Host a web UI in a native window with a secured local server.",
    no_args_is_help=True,
    epilog=_epilog(""),
    rich_markup_mode="rich",
    # run() reports errors briefly; Typer's own traceback would show local variables.
    pretty_exceptions_enable=False,
)

JsonOption = Annotated[bool, typer.Option("--json", help="Output as JSON.")]

# ----- the options both commands share, grouped in the help -----------------------------------

WEB, SERVER, SECURITY, WINDOW, NATIVE = (
    "Web source",
    "Server",
    "Security",
    "Window",
    "Native actions",
)


def _flag(*names: str, help: str, panel: str) -> Any:
    return typer.Option(*names, help=help, rich_help_panel=panel)


SourceArgument = Annotated[
    str | None,
    typer.Argument(
        metavar="[SOURCE]",
        show_default=False,
        help="A folder with the built web bundle, or an http(s) address to open.",
    ),
]
WebDist = Annotated[
    Path | None, _flag("--web-dist", help="Folder with the built web bundle.", panel=WEB)
]
UrlFlag = Annotated[
    str | None,
    _flag("--url", help="Show a page from a server you already run.", panel=WEB),
]
ModeFlag = Annotated[
    options.UrlMode | None,
    _flag(
        "--mode",
        help="For an address: direct (default) or proxy (serve it through Cornea).",
        panel=WEB,
    ),
]
AsgiFlag = Annotated[
    str | None, _flag("--asgi", help="Mount an ASGI app, as module:attribute.", panel=WEB)
]
WsgiFlag = Annotated[
    str | None, _flag("--wsgi", help="Mount a WSGI app, as module:attribute.", panel=WEB)
]
AppDir = Annotated[
    Path | None, _flag("--app-dir", help="Folder to import --asgi/--wsgi apps from.", panel=WEB)
]
PackageFlag = Annotated[
    str | None, _flag("--package", help="Installed package that ships the bundle.", panel=WEB)
]
PackagePath = Annotated[
    str | None,
    _flag("--package-path", help="Bundle folder inside --package (default web/dist).", panel=WEB),
]
SpaFlag = Annotated[
    bool | None,
    _flag("--spa/--no-spa", help="Serve index.html for unknown pages (default on).", panel=WEB),
]
HashedPrefix = Annotated[
    list[str] | None,
    _flag("--hashed-prefix", help="Folder of fingerprinted files to cache. Repeatable.", panel=WEB),
]
Host = Annotated[
    str | None, _flag("--host", help="Address to bind (default 127.0.0.1).", panel=SERVER)
]
Port = Annotated[
    int | None, _flag("--port", help="Port to bind (default: a free one).", panel=SERVER)
]
AllowedHost = Annotated[
    list[str] | None,
    _flag("--allowed-host", help="Extra Host header to accept. Repeatable.", panel=SECURITY),
]
Csp = Annotated[
    str | None,
    _flag("--csp", help="Content-Security-Policy to send (default: strict).", panel=SECURITY),
]
CspProfileFlag = Annotated[
    options.CspProfile | None,
    _flag(
        "--csp-profile",
        help="strict (default), or dev, which allows what dev servers need. For development only.",
        panel=SECURITY,
    ),
]
ApiPrefix = Annotated[
    str | None, _flag("--api-prefix", help="Path prefix of the API (default /api).", panel=SECURITY)
]
TokenTtl = Annotated[
    float | None,
    _flag("--token-ttl", help="Seconds the start-up link works (default 60).", panel=SECURITY),
]
CookieSameSite = Annotated[
    options.SameSite | None,
    _flag("--cookie-samesite", help="SameSite of the session cookie.", panel=SECURITY),
]
PublicPath = Annotated[
    list[str] | None,
    _flag("--public-path", help="Path reachable without a session. Repeatable.", panel=SECURITY),
]
RequireOrigin = Annotated[
    bool | None,
    _flag(
        "--require-origin/--no-require-origin",
        help="Reject state-changing requests without an Origin (default on).",
        panel=SECURITY,
    ),
]
DisableAction = Annotated[
    list[str] | None,
    _flag("--disable-action", help="Switch a built-in action off. Repeatable.", panel=NATIVE),
]
Title = Annotated[str | None, _flag("--title", help="Window title.", panel=WINDOW)]
Size = Annotated[str | None, _flag("--size", help="Window size, like 1200x800.", panel=WINDOW)]
MinSize = Annotated[
    str | None, _flag("--min-size", help="Smallest window size, like 400x300.", panel=WINDOW)
]
Position = Annotated[
    str | None, _flag("--position", help="Window position on screen, like 100,50.", panel=WINDOW)
]
Frameless = Annotated[
    bool | None,
    _flag("--frameless", help="Hide the native title bar; the page draws its own.", panel=WINDOW),
]
Resizable = Annotated[
    bool | None,
    _flag("--resizable/--no-resizable", help="Let the user resize (default on).", panel=WINDOW),
]
OnTop = Annotated[bool | None, _flag("--on-top", help="Keep the window on top.", panel=WINDOW)]
ContextMenu = Annotated[
    bool | None, _flag("--context-menu", help="Allow the right-click menu.", panel=WINDOW)
]
DevTools = Annotated[
    bool | None, _flag("--devtools", help="Allow the developer tools.", panel=WINDOW)
]
Debug = Annotated[
    bool | None,
    _flag("--debug", help="Turn on the context menu and developer tools.", panel=WINDOW),
]


@dataclass
class State:
    """Global options shared with every command through the Typer context."""

    verbose: bool = False
    quiet: bool = False


def _show_version(value: bool) -> None:
    if value:
        output.console.print(f"cornea {__version__}")
        raise typer.Exit


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_show_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show extra detail."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Only show errors."),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Disable colored output."),
    ] = False,
) -> None:
    """Options that apply to every command."""
    if verbose and quiet:
        raise typer.BadParameter("--verbose and --quiet cannot be used together.")
    output.configure(no_color=no_color, verbose=verbose)
    ctx.obj = State(verbose=verbose, quiet=quiet)


@app.command(epilog=_epilog("info"))
def info(json_output: JsonOption = False) -> None:
    """Show version and environment details."""
    details = {
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    if json_output:
        output.console.print_json(data=details)
        return
    table = Table(title="cornea", show_header=False)
    for key, value in details.items():
        table.add_row(key.capitalize(), value)
    output.console.print(table)


# ----- open and serve -------------------------------------------------------------------------


def _launch(
    ctx: typer.Context,
    source: WebSource,
    window: Window | None,
    *,
    server: Server,
    security: Security,
    bridge: Bridge,
) -> None:
    """Run the shell, reporting expected failures as a short error with exit code 1."""
    state = ctx.obj
    assert isinstance(state, State)  # noqa: S101 - set by the callback

    def announce(shell: Shell) -> None:
        # The ready line is data for other programs; the second line is for the person.
        output.console.print(ready_line(shell), soft_wrap=True, markup=False, highlight=False)
        if not state.quiet:
            message = f"Serving {shell.url} - press Ctrl+C to stop"
            output.err_console.print(message, soft_wrap=True, markup=False, highlight=False)

    try:
        run_shell(
            source,
            security=security,
            server=server,
            window=window,
            bridge=bridge,
            on_ready=announce if window is None else None,
        )
    except (ValueError, FileNotFoundError, ImportError, OSError, RuntimeError) as exc:
        output.error(str(exc))
        raise typer.Exit(code=1) from exc


@app.command("open", epilog=_epilog("open"))
def open_window(
    ctx: typer.Context,
    source: SourceArgument = None,
    web_dist: WebDist = None,
    url: UrlFlag = None,
    mode: ModeFlag = None,
    asgi: AsgiFlag = None,
    wsgi: WsgiFlag = None,
    app_dir: AppDir = None,
    package: PackageFlag = None,
    package_path: PackagePath = None,
    spa: SpaFlag = None,
    hashed_prefix: HashedPrefix = None,
    host: Host = None,
    port: Port = None,
    allowed_host: AllowedHost = None,
    csp: Csp = None,
    csp_profile: CspProfileFlag = None,
    api_prefix: ApiPrefix = None,
    token_ttl: TokenTtl = None,
    cookie_samesite: CookieSameSite = None,
    public_path: PublicPath = None,
    require_origin: RequireOrigin = None,
    disable_action: DisableAction = None,
    title: Title = None,
    size: Size = None,
    min_size: MinSize = None,
    position: Position = None,
    frameless: Frameless = None,
    resizable: Resizable = None,
    on_top: OnTop = None,
    context_menu: ContextMenu = None,
    devtools: DevTools = None,
    debug: Debug = None,
) -> None:
    """Show the web UI in a native window (Windows)."""
    try:
        web_source = options.build_source(
            argument=source,
            web_dist=web_dist,
            url=url,
            asgi=asgi,
            wsgi=wsgi,
            app_dir=app_dir,
            package=package,
            package_path=package_path,
            spa=spa,
            hashed_prefix=hashed_prefix,
            mode=mode,
        )
        window = options.build_window(
            title=title,
            size=size,
            min_size=min_size,
            position=position,
            frameless=frameless,
            resizable=resizable,
            on_top=on_top,
            context_menu=context_menu,
            devtools=devtools,
            debug=debug,
        )
        server = options.build_server(host=host, port=port)
        security = options.build_security(
            allowed_host=allowed_host,
            csp=csp,
            api_prefix=api_prefix,
            token_ttl=token_ttl,
            cookie_samesite=cookie_samesite,
            public_path=public_path,
            require_origin=require_origin,
            csp_profile=csp_profile,
        )
        bridge = options.build_bridge(disable_action=disable_action)
    except ValueError as exc:
        output.error(str(exc))
        raise typer.Exit(code=1) from exc
    _launch(ctx, web_source, window, server=server, security=security, bridge=bridge)


@app.command(epilog=_epilog("serve"))
def serve(
    ctx: typer.Context,
    source: SourceArgument = None,
    web_dist: WebDist = None,
    url: UrlFlag = None,
    mode: ModeFlag = None,
    asgi: AsgiFlag = None,
    wsgi: WsgiFlag = None,
    app_dir: AppDir = None,
    package: PackageFlag = None,
    package_path: PackagePath = None,
    spa: SpaFlag = None,
    hashed_prefix: HashedPrefix = None,
    host: Host = None,
    port: Port = None,
    allowed_host: AllowedHost = None,
    csp: Csp = None,
    csp_profile: CspProfileFlag = None,
    api_prefix: ApiPrefix = None,
    token_ttl: TokenTtl = None,
    cookie_samesite: CookieSameSite = None,
    public_path: PublicPath = None,
    require_origin: RequireOrigin = None,
    disable_action: DisableAction = None,
) -> None:
    """Serve the web UI without a window, for a browser or another program.

    Prints one JSON line on stdout with the address (including the one-time start-up token), then
    serves until Ctrl+C.
    """
    try:
        web_source = options.build_source(
            argument=source,
            web_dist=web_dist,
            url=url,
            asgi=asgi,
            wsgi=wsgi,
            app_dir=app_dir,
            package=package,
            package_path=package_path,
            spa=spa,
            hashed_prefix=hashed_prefix,
            mode=mode,
        )
        server = options.build_server(host=host, port=port)
        security = options.build_security(
            allowed_host=allowed_host,
            csp=csp,
            api_prefix=api_prefix,
            token_ttl=token_ttl,
            cookie_samesite=cookie_samesite,
            public_path=public_path,
            require_origin=require_origin,
            csp_profile=csp_profile,
        )
        bridge = options.build_bridge(disable_action=disable_action)
    except ValueError as exc:
        output.error(str(exc))
        raise typer.Exit(code=1) from exc
    _launch(ctx, web_source, None, server=server, security=security, bridge=bridge)


def run() -> None:
    """Console script entry point: run the app and report unexpected errors briefly."""
    try:
        app()
    except Exception as exc:
        output.print_exception(exc)
        raise SystemExit(1) from exc
