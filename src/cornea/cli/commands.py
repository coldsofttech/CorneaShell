"""Command line interface built on Typer and Rich. It only parses input and shows output."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table
from rich.text import Text

from cornea import (
    App,
    Asgi,
    Bridge,
    LogLevel,
    Process,
    Security,
    Server,
    Shell,
    Static,
    Timings,
    Url,
    WebSource,
    Window,
    Wsgi,
    __version__,
    configure_logging,
    ready_line,
)
from cornea import run as run_shell
from cornea.cli import config, options, output
from cornea.core.environment import environment_details
from cornea.core.logs import start_debug_logging
from cornea.core.single_instance import AlreadyRunning

EXAMPLES: dict[str, tuple[str, ...]] = {
    "": ("cornea --version", "cornea --quiet info", "cornea --no-color info"),
    "info": ("cornea info", "cornea info --json"),
    "open": (
        "cornea open web/dist",
        'cornea open web/dist --title "My App" --size 1200x800 --frameless --debug',
        "cornea open http://localhost:5173 --size 1280x800",
        "cornea open http://localhost:5173 --mode proxy --csp-profile dev --frameless",
        'cornea open --run "npm run dev" --url http://localhost:5173 --mode proxy --frameless',
        "cornea open web/dist --app-id com.example.notes --single-instance --remember-window",
        "cornea open web/dist --icon examples/static_html/icon.png",
        "cornea open http://localhost:5173 --frameless --js-api",
        "cornea open web/dist --log-level debug --log-file cornea.log",
        "cornea open web/dist --measure",
        "cornea open web/dist --drop-files --open-files --notifications",
    ),
    "serve": (
        "cornea serve web/dist",
        "cornea serve --asgi myproject.asgi:application --app-dir .",
        "cornea serve web/dist --port 8765 --public-path /health --public-path /status",
        "cornea serve http://localhost:5173 --mode proxy --csp-profile dev",
        "cornea serve web/dist --log-level info --log-file cornea.log",
        "cornea serve web/dist --measure --json-friendly --json-file timings.json",
        'cornea serve --run "npm run dev" --url http://localhost:5173 --mode proxy',
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

WEB, SERVER, SECURITY, WINDOW, NATIVE, APP, LOGGING, MEASURE = (
    "Web source",
    "Server",
    "Security",
    "Window",
    "Native actions",
    "App",
    "Logging",
    "Start-up time",
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
RunFlag = Annotated[
    str | None,
    _flag(
        "--run",
        help="Start this dev-server command for --url and stop it with the window.",
        panel=WEB,
    ),
]
RunCwd = Annotated[
    Path | None, _flag("--run-cwd", help="Folder to run the --run command in.", panel=WEB)
]
RunTimeout = Annotated[
    float | None,
    _flag("--run-timeout", help="Seconds to wait for --url to answer (default 30).", panel=WEB),
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
OpenFiles = Annotated[
    bool | None,
    _flag(
        "--open-files",
        help="Let the page open a file in its program and show it in Explorer.",
        panel=NATIVE,
    ),
]
Notifications = Annotated[
    bool | None,
    _flag(
        "--notifications",
        help="Let the page show Windows notifications (needs the notifications extra).",
        panel=NATIVE,
    ),
]
DropFiles = Annotated[
    bool | None,
    _flag(
        "--drop-files",
        help="Tell the page the full paths of files dropped on the window.",
        panel=WINDOW,
    ),
]
IconFlag = Annotated[
    Path | None,
    _flag("--icon", help="Window and taskbar icon: .ico, .png, .bmp, .gif or .jpg.", panel=WINDOW),
]
JsApi = Annotated[
    bool | None,
    _flag(
        "--js-api",
        help="Give the page the window controls and native actions. Trusted pages only.",
        panel=WINDOW,
    ),
]
AppIdFlag = Annotated[
    str | None,
    _flag("--app-id", help="Name of the app, like com.example.notes.", panel=APP),
]
SingleInstanceFlag = Annotated[
    bool | None,
    _flag("--single-instance", help="Run one copy; a second start shows the first.", panel=APP),
]
RememberWindowFlag = Annotated[
    bool | None,
    _flag("--remember-window", help="Reopen the window where it was, at its size.", panel=APP),
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
    _flag(
        "--debug",
        help="Turn on the context menu, the developer tools and debug logging.",
        panel=WINDOW,
    ),
]
LogLevelFlag = Annotated[
    options.LogLevelChoice | None,
    _flag(
        "--log-level",
        help="Show log messages of this level and above on stderr (default: warning).",
        panel=LOGGING,
    ),
]
MeasureFlag = Annotated[
    bool | None,
    _flag(
        "--measure",
        help="Print how long start-up took (on stderr) once the first page has loaded.",
        panel=MEASURE,
    ),
]
JsonFriendlyFlag = Annotated[
    bool | None,
    _flag(
        "--json-friendly",
        help="With --measure: print the timings as one JSON line on stdout instead.",
        panel=MEASURE,
    ),
]
JsonFileFlag = Annotated[
    Path | None,
    _flag(
        "--json-file",
        help="With --measure: also write the timings as JSON to this file.",
        panel=MEASURE,
    ),
]
LogFileFlag = Annotated[
    Path | None,
    _flag("--log-file", help="Also write a full debug log to this file.", panel=LOGGING),
]


@dataclass
class State:
    """Global options shared with every command through the Typer context."""

    verbose: bool = False
    quiet: bool = False
    config: Path | None = None


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
    config_file: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="Read settings from this file instead of searching for cornea.toml.",
        ),
    ] = None,
    no_config: Annotated[
        bool,
        typer.Option("--no-config", help="Ignore any cornea.toml or [tool.cornea] settings."),
    ] = False,
) -> None:
    """Options that apply to every command."""
    if verbose and quiet:
        raise typer.BadParameter("--verbose and --quiet cannot be used together.")
    if config_file is not None and no_config:
        raise typer.BadParameter("--config and --no-config cannot be used together.")
    output.configure(no_color=no_color, verbose=verbose)
    state = State(verbose=verbose, quiet=quiet)
    ctx.obj = state
    if no_config or ctx.invoked_subcommand not in {"open", "serve"}:
        return
    try:
        found = config_file if config_file is not None else config.find_config(Path.cwd())
        if found is not None:
            ctx.default_map = config.load_config(found)
            state.config = found
    except config.ConfigError as exc:
        output.error(str(exc))
        raise typer.Exit(code=2) from exc


@app.command(epilog=_epilog("info"))
def info(json_output: JsonOption = False) -> None:
    """Show version and environment details."""
    details = environment_details()
    if json_output:
        output.console.print_json(data=details)
        return
    table = Table(title="cornea", show_header=False)
    for key, value in details.items():
        table.add_row(key.capitalize(), value)
    output.console.print(table)


# ----- open and serve -------------------------------------------------------------------------


def _logging_options(
    level: options.LogLevelChoice | None, file: Path | None, debug: bool | None
) -> tuple[LogLevel, Path | None, bool] | None:
    """The level, the file, and whether to use the default file, or None to leave logging alone.

    ``--debug`` means debug logging unless ``--log-level`` says otherwise, and then it also
    writes the default log file unless ``--log-file`` names another file.
    """
    if level is not None:
        return level.value, file, False
    if debug:
        return "debug", file, file is None
    return ("warning", file, False) if file is not None else None


def _source_arguments(ctx: typer.Context, source: str | None, **values: Any) -> dict[str, Any]:
    """The source settings, with the settings file stepping aside for a source on the command line.

    The file may say what to show, but a source typed on the command line replaces everything
    the file said about the source, so the two never mix into something neither meant.
    """

    def came_from(name: str) -> str | None:
        found = ctx.get_parameter_source(name)
        return found.name if found is not None else None

    typed = source is not None or any(
        came_from(name) == "COMMANDLINE" for name in ("web_dist", "url", "asgi", "wsgi", "run")
    )
    if typed:
        for name in config.SOURCE_PARAMETERS:
            if came_from(name) == "DEFAULT_MAP":
                values[name] = None
    return values


def _measure_option(
    measure: bool | None, json_friendly: bool | None, json_file: Path | None
) -> bool | Callable[[Timings], None]:
    """What to pass as ``measure``: False, or our reporter, which prints a Rich table."""
    if not measure:
        if json_friendly or json_file is not None:
            raise typer.BadParameter("--json-friendly and --json-file need --measure")
        return False

    def report(timings: Timings) -> None:
        text = json.dumps(timings.as_dict())
        if json_file is not None:
            try:
                json_file.parent.mkdir(parents=True, exist_ok=True)
                json_file.write_text(text + "\n", encoding="utf-8")
            except OSError as exc:
                output.error(f"could not write the timings: {exc}")
        if json_friendly:
            output.console.print(text, soft_wrap=True, markup=False, highlight=False)
        else:
            table = Table(title="Start-up time", title_justify="left")
            table.add_column("Step")
            table.add_column("Seconds", justify="right")
            for step, seconds in timings.as_dict().items():
                if seconds is not None:
                    table.add_row(step, f"{seconds:.3f}")
            output.err_console.print(table)

    return report


def _describe_source(source: WebSource) -> str:
    """One line that says what is shown, for the details table."""
    match source:
        case Static():
            return f"folder {source.path}" if source.path is not None else "built web bundle"
        case Url():
            return f"{source.url} ({source.mode})"
        case Process():
            command = (
                source.command if isinstance(source.command, str) else " ".join(source.command)
            )
            return f"{source.url} ({source.mode}), started with: {command}"
        case Asgi():
            return f"ASGI app {source.target}"
        case Wsgi():
            return f"WSGI app {source.target}"
        case _:
            return type(source).__name__


def _show_details(
    command: str,
    source: WebSource,
    window: Window | None,
    identity: App | None,
    logging: tuple[LogLevel, Path | None] | None,
    settings_file: Path | None,
) -> None:
    rows = [("Source", _describe_source(source))]
    if settings_file is not None:
        rows.insert(0, ("Settings", str(settings_file)))
    if window is not None:
        shown = f"{window.title!r}, {'frameless' if window.frameless else 'normal frame'}"
        rows.append(("Window", shown))
    if identity is not None and identity.id is not None:
        flags = [
            name
            for name, on in (
                ("single instance", identity.single_instance),
                ("remembers its window", identity.remember_window),
            )
            if on
        ]
        rows.append(("App", ", ".join([identity.id, *flags])))
    if logging is not None:
        level, file = logging
        rows.append(("Logging", f"{level}" + (f", file {file}" if file is not None else "")))
    output.details(f"cornea {command}", rows)


def _launch(
    ctx: typer.Context,
    source: WebSource,
    window: Window | None,
    *,
    server: Server,
    security: Security,
    bridge: Bridge,
    identity: App | None = None,
    logging_options: tuple[LogLevel, Path | None, bool] | None = None,
    measure: bool | Callable[[Timings], None] = False,
) -> None:
    """Run the shell, reporting expected failures as a short error with exit code 1."""
    state = ctx.obj
    assert isinstance(state, State)  # noqa: S101 - set by the callback
    logging_shown: tuple[LogLevel, Path | None] | None = None
    if logging_options is not None:
        level, file, use_default = logging_options
        try:
            if use_default:
                file = start_debug_logging()  # falls back to the screen if it cannot write
            else:
                configure_logging(level, file=file)
        except OSError as exc:
            output.error(f"could not open the log file: {exc}")
            raise typer.Exit(code=1) from exc
        logging_shown = (level, file)
    if not state.quiet:
        _show_details(
            "open" if window is not None else "serve",
            source,
            window,
            identity,
            logging_shown,
            state.config,
        )

    def announce(shell: Shell) -> None:
        # The ready line is data for other programs; the second line is for the person.
        output.console.print(ready_line(shell), soft_wrap=True, markup=False, highlight=False)
        if not state.quiet:
            message = Text.assemble("Serving ", (shell.url, "bold"), " - press Ctrl+C to stop")
            output.err_console.print(message, soft_wrap=True)

    try:
        run_shell(
            source,
            security=security,
            server=server,
            window=window,
            bridge=bridge,
            identity=identity,
            measure=measure,
            on_ready=announce if window is None else None,
        )
    except AlreadyRunning as exc:
        if not exc.activated:
            output.error(str(exc))
            raise typer.Exit(code=1) from exc
        # Handing over to the first copy is what the user asked for, not a failure.
        output.err_console.print(str(exc), soft_wrap=True, markup=False, highlight=False)
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
    run: RunFlag = None,
    run_cwd: RunCwd = None,
    run_timeout: RunTimeout = None,
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
    open_files: OpenFiles = None,
    notifications: Notifications = None,
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
    js_api: JsApi = None,
    drop_files: DropFiles = None,
    icon: IconFlag = None,
    app_id: AppIdFlag = None,
    single_instance: SingleInstanceFlag = None,
    remember_window: RememberWindowFlag = None,
    log_level: LogLevelFlag = None,
    log_file: LogFileFlag = None,
    measure: MeasureFlag = None,
    json_friendly: JsonFriendlyFlag = None,
    json_file: JsonFileFlag = None,
) -> None:
    """Show the web UI in a native window (Windows)."""
    try:
        web_source = options.build_source(
            argument=source,
            **_source_arguments(
                ctx,
                source,
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
                run=run,
                run_cwd=run_cwd,
                run_timeout=run_timeout,
            ),
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
            js_api=js_api,
            drop_files=drop_files,
            icon=icon,
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
        bridge = options.build_bridge(
            disable_action=disable_action, open_files=open_files, notifications=notifications
        )
        identity = options.build_app(
            app_id=app_id, single_instance=single_instance, remember_window=remember_window
        )
    except ValueError as exc:
        output.error(str(exc))
        raise typer.Exit(code=1) from exc
    _launch(
        ctx,
        web_source,
        window,
        server=server,
        security=security,
        bridge=bridge,
        identity=identity,
        logging_options=_logging_options(log_level, log_file, debug),
        measure=_measure_option(measure, json_friendly, json_file),
    )


@app.command(epilog=_epilog("serve"))
def serve(
    ctx: typer.Context,
    source: SourceArgument = None,
    web_dist: WebDist = None,
    url: UrlFlag = None,
    mode: ModeFlag = None,
    run: RunFlag = None,
    run_cwd: RunCwd = None,
    run_timeout: RunTimeout = None,
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
    open_files: OpenFiles = None,
    notifications: Notifications = None,
    log_level: LogLevelFlag = None,
    log_file: LogFileFlag = None,
    measure: MeasureFlag = None,
    json_friendly: JsonFriendlyFlag = None,
    json_file: JsonFileFlag = None,
) -> None:
    """Serve the web UI without a window, for a browser or another program.

    Prints one JSON line on stdout with the address (including the one-time start-up token), then
    serves until Ctrl+C.
    """
    try:
        web_source = options.build_source(
            argument=source,
            **_source_arguments(
                ctx,
                source,
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
                run=run,
                run_cwd=run_cwd,
                run_timeout=run_timeout,
            ),
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
        bridge = options.build_bridge(
            disable_action=disable_action, open_files=open_files, notifications=notifications
        )
    except ValueError as exc:
        output.error(str(exc))
        raise typer.Exit(code=1) from exc
    _launch(
        ctx,
        web_source,
        None,
        server=server,
        security=security,
        bridge=bridge,
        logging_options=_logging_options(log_level, log_file, None),
        measure=_measure_option(measure, json_friendly, json_file),
    )


def run() -> None:
    """Console script entry point: run the app and report unexpected errors briefly."""
    try:
        app()
    except Exception as exc:
        output.print_exception(exc)
        raise SystemExit(1) from exc
