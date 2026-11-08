"""``cornea serve``: serve the web UI without a window."""

import typer

from cornea import preload
from cornea.cli import options, output
from cornea.cli.commands import (
    AllowedHost,
    ApiPrefix,
    AppDir,
    AsgiFlag,
    CookieSameSite,
    Csp,
    CspProfileFlag,
    DisableAction,
    HashedPrefix,
    Host,
    JsonFileFlag,
    JsonFriendlyFlag,
    LogFileFlag,
    LogLevelFlag,
    MeasureFlag,
    ModeFlag,
    Notifications,
    OpenFiles,
    PackageFlag,
    PackagePath,
    Port,
    PublicPath,
    RequireOrigin,
    RunCwd,
    RunFlag,
    RunTimeout,
    SourceArgument,
    SpaFlag,
    TokenTtl,
    UrlFlag,
    WebDist,
    WsgiFlag,
    app,
    epilog,
    launch,
    logging_options,
    measure_option,
    source_arguments,
)


@app.command(epilog=epilog("serve"))
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
    preload()  # load the server while the options below are read
    try:
        web_source = options.build_source(
            argument=source,
            **source_arguments(
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
    launch(
        ctx,
        web_source,
        None,
        server=server,
        security=security,
        bridge=bridge,
        logging_options=logging_options(log_level, log_file, None),
        measure=measure_option(measure, json_friendly, json_file),
    )
