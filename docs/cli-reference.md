# CLI reference

<!-- The usage, options and examples between the GENERATED markers are written by scripts/gen_cli_reference.py from the CLI. Edit everything else by hand. -->

`cornea` is a command line tool built with [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/).

## Running

```bash
cornea --help          # installed script
python -m cornea.cli       # without relying on the script being on PATH
uvx --from cornea-shell cornea --help   # one-off, no install
```

## Global options

These go before the command name, for example `cornea --quiet doctor`.

| Option | Short | Description |
| --- | --- | --- |
| `--help` | | Show help for the tool or for a command. |
| `--version` | `-V` | Show the version and exit. |
| `--verbose` | `-v` | Show extra detail on stderr, and a traceback for unexpected errors. |
| `--quiet` | `-q` | Only show errors. Cannot be combined with `--verbose`. |
| `--no-color` | | Disable colored output. The standard `NO_COLOR` variable has the same effect. |
| `--config PATH` | | Read settings from this file instead of searching for one. |
| `--no-config` | | Ignore any settings file. Cannot be combined with `--config`. |
| `--install-completion` | | Install shell completion for the current shell. |
| `--show-completion` | | Print the completion script instead of installing it. |

## Quick start

```bash
cornea doctor                          # is this machine ready?
cornea open web/dist                   # show a built folder in a window
cornea serve web/dist                  # same page, no window: open the printed address in a browser
cornea open --help                     # every option for a command
```

Every setting of the Python API has a flag, and the settings you type every time can live in a [settings file](#the-settings-file).

## Commands

The options for each command are listed first, as Typer prints them, followed by what they mean and examples. Every example is also run by the test suite (it must at least parse).

### `cornea open`

<!-- BEGIN GENERATED: typer open -->
Show the web UI in a native window (Windows).

**Usage**:

```console
$ cornea open [OPTIONS] [SOURCE]
```

**Arguments**:

* `[SOURCE]`: A folder with the built web bundle, or an http(s) address to open.

**Options**:

* `--web-dist <path>`: Folder with the built web bundle.
* `--url <str>`: Show a page from a server you already run.
* `--mode <direct|proxy>`: For an address: direct (default) or proxy (serve it through Cornea).
* `--run <str>`: Start this dev-server command for --url and stop it with the window.
* `--run-cwd <path>`: Folder to run the --run command in.
* `--run-timeout <float>`: Seconds to wait for --url to answer (default 30).
* `--asgi <str>`: Mount an ASGI app, as module:attribute.
* `--wsgi <str>`: Mount a WSGI app, as module:attribute.
* `--app-dir <path>`: Folder to import --asgi/--wsgi apps from.
* `--package <str>`: Installed package that ships the bundle.
* `--package-path <str>`: Bundle folder inside --package (default web/dist).
* `--spa / --no-spa`: Serve index.html for unknown pages (default on).
* `--hashed-prefix <str>`: Folder of fingerprinted files to cache. Repeatable.
* `--host <str>`: Address to bind (default 127.0.0.1).
* `--port <int>`: Port to bind (default: a free one).
* `--allowed-host <str>`: Extra Host header to accept. Repeatable.
* `--csp <str>`: Content-Security-Policy to send (default: strict).
* `--csp-profile <strict|dev>`: strict (default), or dev, which allows what dev servers need. For development only.
* `--api-prefix <str>`: Path prefix of the API (default /api).
* `--token-ttl <float>`: Seconds the start-up link works (default 60).
* `--cookie-samesite <strict|lax>`: SameSite of the session cookie.
* `--public-path <str>`: Path reachable without a session. Repeatable.
* `--require-origin / --no-require-origin`: Reject state-changing requests without an Origin (default on).
* `--disable-action <str>`: Switch a built-in action off. Repeatable.
* `--open-files`: Let the page open a file in its program and show it in Explorer.
* `--notifications`: Let the page show Windows notifications (needs the notifications extra).
* `--title <str>`: Window title.
* `--size <str>`: Window size, like 1200x800.
* `--min-size <str>`: Smallest window size, like 400x300.
* `--position <str>`: Window position on screen, like 100,50.
* `--frameless`: Hide the native title bar; the page draws its own.
* `--resizable / --no-resizable`: Let the user resize (default on).
* `--on-top`: Keep the window on top.
* `--context-menu`: Allow the right-click menu.
* `--devtools`: Allow the developer tools.
* `--debug`: Turn on the context menu, the developer tools and debug logging.
* `--js-api`: Give the page the window controls and native actions. Trusted pages only.
* `--drop-files`: Tell the page the full paths of files dropped on the window.
* `--downloads`: Let the page download files; the person chooses where to save each one.
* `--icon <path>`: Window and taskbar icon: .ico, .png, .bmp, .gif or .jpg.
* `--app-id <str>`: Name of the app, like com.example.notes.
* `--single-instance`: Run one copy; a second start shows the first.
* `--remember-window`: Reopen the window where it was, at its size.
* `--log-level <debug|info|warning|error>`: Show log messages of this level and above on stderr (default: warning).
* `--log-file <path>`: Also write a full debug log to this file.
* `--measure`: Print how long start-up took (on stderr) once the first page has loaded.
* `--json-friendly`: With --measure: print the timings as one JSON line on stdout instead.
* `--json-file <path>`: With --measure: also write the timings as JSON to this file.
* `--help`: Show this message and exit.
<!-- END GENERATED -->

Show the web UI in a native window (Windows). `SOURCE` is a folder with the built bundle, or an `http(s)` address that the window opens directly.

```console
$ cornea open web/dist
$ cornea open web/dist --title "My App" --size 1200x800 --frameless --debug
$ cornea open http://localhost:5173 --size 1280x800
$ cornea open web/dist --app-id com.example.notes --single-instance --remember-window
$ cornea open web/dist --icon examples/static_html/icon.png
```

By default an address is opened **directly**: the page is not served by Cornea, so it skips Cornea's security, needs the normal window frame (`--frameless` is an error) and cannot use the window controls. With `--mode proxy` (needs `pip install "cornea-shell[proxy]"`) Cornea serves the page from its own address instead, so it gets the security, the window controls and the frameless window, and a dev server's hot reload keeps working:

```console
$ npm run dev
$ cornea open http://localhost:5173 --mode proxy --csp-profile dev --frameless
```

A dev server injects inline scripts and styles, which the default content security policy blocks. `--csp-profile dev` allows exactly that and nothing else. It is for development only.

A directly opened address cannot be frameless, because its page cannot reach Cornea's window routes. `--js-api` lifts that rule: it gives the page `window.pywebview.api` with the window controls and the native actions.

```console
$ cornea open http://localhost:5173 --frameless --js-api
```

pywebview puts that object into every page the window loads, including one it later navigates to, so the page gets the window controls and the native actions (dialogs, opening a link, platform information). Use `--js-api` only for pages you trust. You can still switch off single actions with `--disable-action`. `--mode proxy` is the alternative that needs no `--js-api`.

### `cornea doctor`

<!-- BEGIN GENERATED: typer doctor -->
Check that this machine is ready to show a Cornea window.

**Usage**:

```console
$ cornea doctor [OPTIONS]
```

**Options**:

* `--port <int>`: Check that this port is free on 127.0.0.1 (0 checks that one can be opened).  [default: 0]
* `--json`: Output as JSON.
* `--help`: Show this message and exit.
<!-- END GENERATED -->

Check that this machine is ready, and show what Cornea runs on: the Cornea and Python versions, the platform, the WebView2 runtime and pywebview (on Windows), the optional extras, the settings file (read and checked), a loopback port that can be opened, and the log folder. Each line is `ok`, a `warning` (worth knowing) or a `problem`. The exit code is 1 if there is a problem and 0 otherwise.

```console
$ cornea doctor
$ cornea doctor --port 8765 --json
```

`--port N` checks that port `N` is free on `127.0.0.1`. `--json` prints a list of `{name, status, detail}` for other programs.

### `cornea serve`

<!-- BEGIN GENERATED: typer serve -->
Serve the web UI without a window, for a browser or another program.

Prints one JSON line on stdout with the address (including the one-time start-up token), then
serves until Ctrl+C.

**Usage**:

```console
$ cornea serve [OPTIONS] [SOURCE]
```

**Arguments**:

* `[SOURCE]`: A folder with the built web bundle, or an http(s) address to open.

**Options**:

* `--web-dist <path>`: Folder with the built web bundle.
* `--url <str>`: Show a page from a server you already run.
* `--mode <direct|proxy>`: For an address: direct (default) or proxy (serve it through Cornea).
* `--run <str>`: Start this dev-server command for --url and stop it with the window.
* `--run-cwd <path>`: Folder to run the --run command in.
* `--run-timeout <float>`: Seconds to wait for --url to answer (default 30).
* `--asgi <str>`: Mount an ASGI app, as module:attribute.
* `--wsgi <str>`: Mount a WSGI app, as module:attribute.
* `--app-dir <path>`: Folder to import --asgi/--wsgi apps from.
* `--package <str>`: Installed package that ships the bundle.
* `--package-path <str>`: Bundle folder inside --package (default web/dist).
* `--spa / --no-spa`: Serve index.html for unknown pages (default on).
* `--hashed-prefix <str>`: Folder of fingerprinted files to cache. Repeatable.
* `--host <str>`: Address to bind (default 127.0.0.1).
* `--port <int>`: Port to bind (default: a free one).
* `--allowed-host <str>`: Extra Host header to accept. Repeatable.
* `--csp <str>`: Content-Security-Policy to send (default: strict).
* `--csp-profile <strict|dev>`: strict (default), or dev, which allows what dev servers need. For development only.
* `--api-prefix <str>`: Path prefix of the API (default /api).
* `--token-ttl <float>`: Seconds the start-up link works (default 60).
* `--cookie-samesite <strict|lax>`: SameSite of the session cookie.
* `--public-path <str>`: Path reachable without a session. Repeatable.
* `--require-origin / --no-require-origin`: Reject state-changing requests without an Origin (default on).
* `--disable-action <str>`: Switch a built-in action off. Repeatable.
* `--open-files`: Let the page open a file in its program and show it in Explorer.
* `--notifications`: Let the page show Windows notifications (needs the notifications extra).
* `--log-level <debug|info|warning|error>`: Show log messages of this level and above on stderr (default: warning).
* `--log-file <path>`: Also write a full debug log to this file.
* `--measure`: Print how long start-up took (on stderr) once the first page has loaded.
* `--json-friendly`: With --measure: print the timings as one JSON line on stdout instead.
* `--json-file <path>`: With --measure: also write the timings as JSON to this file.
* `--help`: Show this message and exit.
<!-- END GENERATED -->

Serve the web UI without a window, for a browser or another program. It prints one JSON line to stdout and then serves until you press Ctrl+C:

```console
$ cornea serve web/dist
{"event": "ready", "url": "http://127.0.0.1:52817/?cornea_token=...", "port": 52817, "window": false}
Serving http://127.0.0.1:52817/?cornea_token=... - press Ctrl+C to stop
```

The JSON line is for other programs; the second line goes to stderr for people and is hidden by `--quiet`. Open the `url` in a browser once: it carries a one-time token that is exchanged for a session cookie. The window controls still answer from a stand-in window, and dialogs report that they are unavailable.

## Options by topic

### Choosing the web source

Give exactly one of these (or the `SOURCE` argument, which is `--web-dist` for a folder and `--url` for an address):

| Option | Source |
| --- | --- |
| `--web-dist FOLDER` | A built bundle. With none of these, Cornea looks for `web/dist` (or the bundle of `--package`). |
| `--url ADDRESS` | A page from a server you already run. Direct by default, which needs `open`; `--mode proxy` also works with `serve`. |
| `--run COMMAND` | A dev-server command that Cornea starts. Needs `--url` with the address it serves on. |
| `--asgi module:attr` | An ASGI app (FastAPI, Django ASGI) mounted on the server. |
| `--wsgi module:attr` | A WSGI app (Flask, Django) mounted on the server. |

`--run` starts the command (a string, run through the shell, so `npm run dev` works), waits until the address answers, and shows it as `--url` does, directly or with `--mode proxy`. It cannot be combined with `--web-dist`, `--asgi` or `--wsgi`. `--run-cwd FOLDER` is where the command runs and `--run-timeout SECONDS` is how long to wait for the address (30 by default). When Cornea stops, or crashes, the command and everything it started are stopped too.

```console
$ cornea open --run "npm run dev" --url http://localhost:5173 --mode proxy --csp-profile dev --frameless
```

Failures print one short message and exit with code 1: the command ended before the address answered (the message includes the command's last output), the address did not answer in time, something is already listening on that address, or the program could not be started.

`--app-dir` adds a folder to the import path for `--asgi` and `--wsgi`. `--package`, `--package-path`, `--spa/--no-spa` and `--hashed-prefix` only apply to a bundle.

### Other options

Every setting of the Python API has a flag, grouped in `--help`: server (`--host`, `--port`), security (`--allowed-host`, `--csp`, `--csp-profile`, `--api-prefix`, `--token-ttl`, `--cookie-samesite`, `--public-path`, `--require-origin/--no-require-origin`), native actions (`--disable-action`) and, for `open`, the window (`--title`, `--size`, `--min-size`, `--position`, `--frameless`, `--icon`, `--js-api`, `--resizable/--no-resizable`, `--on-top`, `--context-menu`, `--devtools`, `--debug`) files and notifications (`--drop-files`, `--downloads`, `--open-files`, `--notifications`), the app (`--app-id`, `--single-instance`, `--remember-window`) and logging (`--log-level`, `--log-file`). Sizes look like `1200x800` and positions like `100,50`. The context menu and developer tools stay off unless you ask for them or use `--debug`. The command line never reads environment variables.

### The app (`open` only)

| Option | Effect |
| --- | --- |
| `--app-id ID` | Names the app, like `com.example.notes`: letters, digits, `.`, `-` and `_`. It also sets the Windows taskbar identity, so the icon is not grouped under `python.exe`. |
| `--single-instance` | Run one copy at a time. Needs `--app-id`. |
| `--remember-window` | Reopen the window at its last size, position and maximized state. Needs `--app-id`. |

The app keeps its files in `%LOCALAPPDATA%\Cornea\<id>\`. A second launch of a single-instance app brings the first window to the front (restoring it if minimized), prints a message and exits with code `0`. If it cannot reach the first copy it exits with code `1`.

### Logging

| Option | Effect |
| --- | --- |
| `--log-level LEVEL` | Show log messages of this level and above on stderr: `debug`, `info`, `warning` (the default) or `error`. |
| `--log-file PATH` | Also write a full debug log to this file. The folder is created if needed. |

`--debug` (for `open`) also turns on debug logging, unless `--log-level` says otherwise. With no `--log-file`, it writes the log to `%LOCALAPPDATA%\Cornea\logs\cornea.log` (the folder is created; the file is started over at 1 MB, keeping three older ones). If that file cannot be written, debug messages only go to stderr. An unwritable log file is an error before anything starts. Logs go to stderr, so the JSON line of `serve` on stdout stays clean. The start-up token is never written.

```console
$ cornea open web/dist --log-level debug --log-file cornea.log
```

### Start-up time

| Option | Effect |
| --- | --- |
| `--measure` | Show how long start-up took, as a table on stderr, once the first page has loaded (or once the server answers, for `serve`). |
| `--json-friendly` | With `--measure`: print the timings as one JSON line on stdout instead of the table. |
| `--json-file PATH` | With `--measure`: also write the timings as JSON to this file. |

The steps are `process_ready` (only with `--run`), `server_ready`, `window_shown` and `page_loaded`, in seconds since the command started working, and `null` for a step that did not happen. For `serve`, `--json-friendly` adds a second JSON line after the ready line. The `--json-friendly` and `--json-file` options need `--measure`. To compare runs, run the command several times with `--json-file`.

```console
$ cornea open web/dist --measure
$ cornea serve web/dist --measure --json-friendly --json-file timings.json
```

### Files (`open` only)

| Option | Effect |
| --- | --- |
| `--downloads` | Let the page download files. Each download opens a save dialog. Off by default. |
| `--drop-files` | Tell the page the full paths of files dropped on the window, as a `cornea:drop` event. Off by default. |
| `--notifications` | Add the `show_notification` action, which shows a Windows notification (needs `pip install "cornea-shell[notifications]"`). Off by default. |
| `--open-files` | Add the `open_file` and `reveal` actions. Off by default. Works with `serve` too, where Windows cannot open files, so they report that they are unavailable. |

`open_file` refuses programs, scripts and shortcuts, network paths, folders and missing files. `reveal` shows any existing path in Explorer without running it.

### The window icon (`open` only)

`--icon PATH` shows an icon on the window and its taskbar button. `.ico`, `.png`, `.bmp`, `.gif`, `.jpg` and `.jpeg` files are accepted. A missing file is an error before anything starts; a file that cannot be loaded only logs a warning.

## Recipes

Each recipe is complete: copy it, change the paths. The [examples](../examples) folder has a runnable project for each.

### A built React, Vue or plain HTML folder

```console
$ cd my-ui && npm run build
$ cornea open my-ui/dist --title "My App" --size 1200x800
```

Add `--frameless` if the page draws its own title bar.

### A dev server with hot reload

```console
$ cornea open --run "npm run dev" --url http://localhost:5173 --mode proxy --csp-profile dev --frameless
```

Cornea starts the command, waits for the address, shows it, and stops the command with the window. `--csp-profile dev` is for development only, because dev servers inject inline scripts. Proxy mode needs `pip install "cornea-shell[proxy]"`.

### A FastAPI, Flask or Django app

```console
$ cornea open --asgi main:app --app-dir path/to/project               # FastAPI, Django ASGI
$ cornea open --wsgi flask_example:app --app-dir path/to/project      # Flask, Django WSGI
```

`--app-dir` is the folder the module is imported from. `/api` and `/health` belong to Cornea; your routes can be anywhere else.

### A page in a browser, or a script

```console
$ cornea serve web/dist
{"event": "ready", "url": "http://127.0.0.1:52817/?cornea_token=...", "port": 52817, "window": false}
```

Open the `url` once in a browser. A script can read the JSON line from stdout and use the `port`.

### A real app: one copy, remembered window, notifications

```console
$ cornea open web/dist --app-id com.example.notes --single-instance --remember-window \
    --notifications --open-files --drop-files --downloads --icon icon.png
```

The page can then call `show_notification`, `open_file` and `reveal`, hear `cornea:drop`, and save downloads through a dialog. Nothing here is on unless you ask.

### Find out why something does not work

```console
$ cornea doctor
$ cornea open web/dist --log-level debug --log-file cornea.log
```

`doctor` checks WebView2, ports, the settings file and the log folder. The log file has everything, with the start-up token hidden, and is the thing to attach to a bug report.

## The settings file

Settings you would otherwise type every time can live in a file. Cornea looks for `cornea.toml` in the current folder and then in each folder above it, and in the same places for a `[tool.cornea]` table in `pyproject.toml`. In one folder `cornea.toml` wins. The first file found is used on its own; files are never merged. Only the command line reads it: a Python program that calls `Shell` or `run()` stays explicit.

Each table holds the long flags of `open` and `serve`, without the leading dashes. Dashes or underscores both work in a name. A single value is accepted where a flag can repeat (`allowed-host`, `public-path`, `disable-action`).

```toml
[source]        # web-dist, url, mode, run, run-cwd, run-timeout, asgi, wsgi, app-dir,
run = "npm run dev"       # package, package-path, spa, hashed-prefix
url = "http://localhost:5173"
mode = "proxy"

[server]        # host, port
[security]      # allowed-host, csp, csp-profile, api-prefix, token-ttl, cookie-samesite,
csp-profile = "dev"       # public-path, require-origin
[bridge]        # disable-action

[window]        # title, size, min-size, position, frameless, resizable, on-top,
title = "My App"          # context-menu, devtools, debug, js-api, icon
frameless = true

[app]           # id, single-instance, remember-window
id = "com.example.notes"

[logging]       # level, file
level = "info"
```

In `pyproject.toml` the same tables are written as `[tool.cornea.window]` and so on. Paths in the file are relative to the file. A flag on the command line always wins. A source on the command line (a folder, `--url`, `--run`, `--asgi`, `--wsgi`) replaces everything the file said under `[source]`, so the two never mix. A table or key the command does not know is an error (exit code 2), and so is a file that is not valid TOML. `open` and `serve` show the file they used in their details table.

## What the commands print

`open` and `serve` first show a small table on stderr with what they are about to do: the source, the window, the app and the logging. `--quiet` hides it. `info`, the details table and `--measure` all use Rich, so they follow `--no-color` and `NO_COLOR`. Data for other programs (the `serve` ready line, `info --json`, `--json-friendly`) is plain JSON on stdout.

## Output conventions

- Results go to **stdout**, so they can be piped.
- Errors and extra detail go to **stderr**.
- `--json` prints a single JSON document to stdout, even with `--quiet`.
- Color is turned off automatically when output is piped, when `NO_COLOR` is set, or with `--no-color`.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. Also when a second start of a `--single-instance` app handed over to the first. |
| `1` | The command failed, for example a missing bundle, a setting that is not allowed, or an unexpected error. |
| `2` | Invalid usage, such as an unknown option or conflicting options. |

## Errors

Expected failures print `Error: <message>` to stderr and exit with code 1. Unexpected exceptions are caught by `run()` in `commands.py`: they print a one-line message and a hint to stderr, and show a traceback only with `--verbose`. Local variables are never shown, because they can contain secrets.

## Adding a command

1. Add the logic to `cornea.core` as a plain function that returns a value or raises an exception. It must not print or exit.
2. Add a command to `src/cornea/cli/commands.py` that calls it, writes through the consoles in `output.py`, and raises `typer.Exit(code=1)` on failure.
3. Add a `--json` option if the command returns data.
4. Add tests with `typer.testing.CliRunner`, add the command and its examples to `EXAMPLES` in `commands.py`, describe it in `scripts/cli_reference.md` (with a generated block, like the ones above, where its options go), and regenerate this file with `uv run python scripts/gen_cli_reference.py`. CI fails if the committed copy is out of date.

<!-- BEGIN GENERATED: examples -->
## Examples

Every command, as registered in the CLI and run by the tests.

### `cornea`

```console
$ cornea --version
$ cornea --quiet doctor
$ cornea --no-color doctor
```

### `cornea doctor`

```console
$ cornea doctor
$ cornea doctor --port 8765 --json
```

### `cornea open`

```console
$ cornea open web/dist
$ cornea open web/dist --title "My App" --size 1200x800 --frameless --debug
$ cornea open http://localhost:5173 --size 1280x800
$ cornea open http://localhost:5173 --mode proxy --csp-profile dev --frameless
$ cornea open --run "npm run dev" --url http://localhost:5173 --mode proxy --frameless
$ cornea open web/dist --app-id com.example.notes --single-instance --remember-window
$ cornea open web/dist --icon examples/static_html/icon.png
$ cornea open http://localhost:5173 --frameless --js-api
$ cornea open web/dist --log-level debug --log-file cornea.log
$ cornea open web/dist --measure
$ cornea open web/dist --drop-files --open-files --notifications
```

### `cornea serve`

```console
$ cornea serve web/dist
$ cornea serve --asgi myproject.asgi:application --app-dir .
$ cornea serve web/dist --port 8765 --public-path /health --public-path /status
$ cornea serve http://localhost:5173 --mode proxy --csp-profile dev
$ cornea serve web/dist --log-level info --log-file cornea.log
$ cornea serve web/dist --measure --json-friendly --json-file timings.json
$ cornea serve --run "npm run dev" --url http://localhost:5173 --mode proxy
```
<!-- END GENERATED -->
