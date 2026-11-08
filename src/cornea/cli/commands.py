"""Command line interface built on Typer and Rich. It only parses input and shows output."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.table import Table
from rich.text import Text

from cornea import (
    App,
    Asgi,
    Bridge,
    Loading,
    LogLevel,
    Process,
    Security,
    Server,
    Static,
    Url,
    WebSource,
    Window,
    Wsgi,
    __version__,
)
from cornea.cli import config, options, output
from cornea.core.logs import Logs
from cornea.core.security.single_instance import AlreadyRunning

if TYPE_CHECKING:
    # Importing these loads the server libraries, which `--version` and `doctor` do not need.
    from cornea import Shell, Timings

EXAMPLES: dict[str, tuple[str, ...]] = {
    "": ("cornea --version", "cornea --quiet doctor", "cornea --no-color doctor"),
    "doctor": ("cornea doctor", "cornea doctor --port 8765 --json"),
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


def epilog(command: str) -> str:
    """Help footer that lists the examples for ``command``."""
    return "[bold]Examples[/bold]\n\n" + "\n\n".join(f"  $ {line}" for line in EXAMPLES[command])


app = typer.Typer(
    name="cornea",
    help="Host a web UI in a native window with a secured local server.",
    no_args_is_help=True,
    epilog=epilog(""),
    rich_markup_mode="rich",
    # run() reports errors briefly; Typer's own traceback would show local variables.
    pretty_exceptions_enable=False,
)

JsonOption = Annotated[bool, typer.Option("--json", help="Output as JSON.")]

# ----- the options both commands share, grouped in the help -----------------------------------

WEB, SERVER, SECURITY, WINDOW, LOADING, NATIVE, APP, LOGGING, MEASURE = (
    "Web source",
    "Server",
    "Security",
    "Window",
    "Loading screen",
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
Downloads = Annotated[
    bool | None,
    _flag(
        "--downloads",
        help="Let the page download files; the person chooses where to save each one.",
        panel=WINDOW,
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
LoadingFlag = Annotated[
    bool | None,
    _flag(
        "--loading/--no-loading",
        help="Show a loading screen while the app starts (default on).",
        panel=LOADING,
    ),
]
LoadingSubtitle = Annotated[
    str | None,
    _flag("--loading-subtitle", help="Tag line on the loading screen.", panel=LOADING),
]
LoadingTitle = Annotated[
    str | None,
    _flag(
        "--loading-title",
        help="Heading on the loading screen (default: window title).",
        panel=LOADING,
    ),
]
LoadingIcon = Annotated[
    Path | None,
    _flag(
        "--loading-icon",
        help="Picture on the loading screen (default: window icon).",
        panel=LOADING,
    ),
]
LoadingTheme = Annotated[
    str | None,
    _flag("--loading-theme", help="auto, light or dark (default auto).", panel=LOADING),
]
LoadingBackground = Annotated[
    str | None,
    _flag("--loading-background", help="Background colour, like #1a1a1a.", panel=LOADING),
]
LoadingForeground = Annotated[
    str | None,
    _flag("--loading-foreground", help="Text colour, like #ffffff.", panel=LOADING),
]
LoadingMinDisplay = Annotated[
    float | None,
    _flag(
        "--loading-min-display",
        help="Seconds to keep the loading screen up at least (default 0.3).",
        panel=LOADING,
    ),
]
LoadingHtml = Annotated[
    Path | None,
    _flag("--loading-html", help="Your own HTML page to show instead.", panel=LOADING),
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
            defaults = config.load_config(found)
            # A file chosen with --config or sitting in this folder may start a command or import
            # code; one found in a parent folder may not, so a cloned repository cannot run any.
            trusted = config_file is not None or found.parent.resolve() == Path.cwd().resolve()
            if not trusted and config.drop_code(defaults):
                typer.echo(
                    f"Ignoring run, asgi, wsgi and app-dir from {found}: it is in a parent folder. "
                    "Pass them as options or use --config to run code.",
                    err=True,
                )
            ctx.default_map = defaults
            state.config = found
    except config.ConfigError as exc:
        output.error(str(exc))
        raise typer.Exit(code=2) from exc


# ----- open and serve -------------------------------------------------------------------------


def logging_options(
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


def source_arguments(ctx: typer.Context, source: str | None, **values: Any) -> dict[str, Any]:
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


def measure_option(
    measure: bool | None, json_friendly: bool | None, json_file: Path | None
) -> bool | Callable[["Timings"], None]:
    """What to pass as ``measure``: False, or our reporter, which prints a Rich table."""
    if not measure:
        if json_friendly or json_file is not None:
            raise typer.BadParameter("--json-friendly and --json-file need --measure")
        return False

    def report(timings: "Timings") -> None:
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


def run_shell(*args: Any, **kwargs: Any) -> None:
    """Run the shell. ``cornea.run`` is imported here because it loads the server libraries."""
    from cornea import run

    run(*args, **kwargs)


def launch(
    ctx: typer.Context,
    source: WebSource,
    window: Window | None,
    *,
    server: Server,
    security: Security,
    bridge: Bridge,
    identity: App | None = None,
    logging_options: tuple[LogLevel, Path | None, bool] | None = None,
    measure: bool | Callable[["Timings"], None] = False,
    loading: Loading | bool | None = True,
) -> None:
    """Run the shell, reporting expected failures as a short error with exit code 1."""
    from cornea import ready_line

    state = ctx.obj
    assert isinstance(state, State)  # noqa: S101 - set by the callback
    logging_shown: tuple[LogLevel, Path | None] | None = None
    if logging_options is not None:
        level, file, use_default = logging_options
        try:
            if use_default:
                file = Logs.start_debug()  # falls back to the screen if it cannot write
            else:
                Logs.configure(level, file=file)
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

    def announce(shell: "Shell") -> None:
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
            loading=loading,
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


def run() -> None:
    """Console script entry point: run the app and report unexpected errors briefly."""
    try:
        app()
    except Exception as exc:
        output.print_exception(exc)
        raise SystemExit(1) from exc
