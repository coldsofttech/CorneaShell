# CLI reference

`cornea` is a command line tool built with [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/).

## Running

```bash
cornea --help          # installed script
python -m cornea.cli       # without relying on the script being on PATH
uvx --from cornea-shell cornea --help   # one-off, no install
```

## Global options

These go before the command name, for example `cornea --quiet info`.

| Option | Short | Description |
| --- | --- | --- |
| `--help` | | Show help for the tool or for a command. |
| `--version` | `-V` | Show the version and exit. |
| `--verbose` | `-v` | Show extra detail on stderr, and a traceback for unexpected errors. |
| `--quiet` | `-q` | Only show errors. Cannot be combined with `--verbose`. |
| `--no-color` | | Disable colored output. The standard `NO_COLOR` variable has the same effect. |
| `--install-completion` | | Install shell completion for the current shell. |
| `--show-completion` | | Print the completion script instead of installing it. |

The full, generated list of commands and options is in [cli-reference.md](cli-reference.md). Regenerate it after changing a command:

```bash
uv run python scripts/gen_cli_reference.py
```

CI fails if the file is out of date.

## Commands

### `open [SOURCE]`

Show the web UI in a native window (Windows). `SOURCE` is a folder with the built bundle, or an `http(s)` address that the window opens directly.

```console
$ cornea open web/dist
$ cornea open web/dist --title "My App" --size 1200x800 --frameless --debug
$ cornea open http://localhost:5173 --size 1280x800
```

By default an address is opened **directly**: the page is not served by Cornea, so it skips Cornea's security, needs the normal window frame (`--frameless` is an error) and cannot use the window controls. With `--mode proxy` (needs `pip install "cornea-shell[proxy]"`) Cornea serves the page from its own address instead, so it gets the security, the window controls and the frameless window, and a dev server's hot reload keeps working:

```console
$ npm run dev
$ cornea open http://localhost:5173 --mode proxy --csp-profile dev --frameless
```

A dev server injects inline scripts and styles, which the default content security policy blocks. `--csp-profile dev` allows exactly that and nothing else. It is for development only.

### `serve [SOURCE]`

Serve the web UI without a window, for a browser or another program. It prints one JSON line to stdout and then serves until you press Ctrl+C:

```console
$ cornea serve web/dist
{"event": "ready", "url": "http://127.0.0.1:52817/?cornea_token=...", "port": 52817, "window": false}
Serving http://127.0.0.1:52817/?cornea_token=... - press Ctrl+C to stop
```

The JSON line is for other programs; the second line goes to stderr for people and is hidden by `--quiet`. Open the `url` in a browser once: it carries a one-time token that is exchanged for a session cookie. The window controls still answer from a stand-in window, and dialogs report that they are unavailable.

### Choosing the web source

Give exactly one of these (or the `SOURCE` argument, which is `--web-dist` for a folder and `--url` for an address):

| Option | Source |
| --- | --- |
| `--web-dist FOLDER` | A built bundle. With none of these, Cornea looks for `web/dist` (or the bundle of `--package`). |
| `--url ADDRESS` | A page from a server you already run. Direct by default, which needs `open`; `--mode proxy` also works with `serve`. |
| `--asgi module:attr` | An ASGI app (FastAPI, Django ASGI) mounted on the server. |
| `--wsgi module:attr` | A WSGI app (Flask, Django) mounted on the server. |

`--app-dir` adds a folder to the import path for `--asgi` and `--wsgi`. `--package`, `--package-path`, `--spa/--no-spa` and `--hashed-prefix` only apply to a bundle.

### Other options

Every setting of the Python API has a flag, grouped in `--help`: server (`--host`, `--port`), security (`--allowed-host`, `--csp`, `--csp-profile`, `--api-prefix`, `--token-ttl`, `--cookie-samesite`, `--public-path`, `--require-origin/--no-require-origin`), native actions (`--disable-action`) and, for `open`, the window (`--title`, `--size`, `--min-size`, `--position`, `--frameless`, `--resizable/--no-resizable`, `--on-top`, `--context-menu`, `--devtools`, `--debug`). Sizes look like `1200x800` and positions like `100,50`. The context menu and developer tools stay off unless you ask for them or use `--debug`. The command line never reads environment variables.

### `info`

Show the tool version, the Python version and the platform in a table. Add `--json` for machine-readable output.

## Output conventions

- Results go to **stdout**, so they can be piped.
- Errors and extra detail go to **stderr**.
- `--json` prints a single JSON document to stdout, even with `--quiet`.
- Color is turned off automatically when output is piped, when `NO_COLOR` is set, or with `--no-color`.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | The command failed, for example a missing bundle, a setting that is not allowed, or an unexpected error. |
| `2` | Invalid usage, such as an unknown option or conflicting options. |

## Errors

Expected failures print `Error: <message>` to stderr and exit with code 1. Unexpected exceptions are caught by `run()` in `commands.py`: they print a one-line message and a hint to stderr, and show a traceback only with `--verbose`. Local variables are never shown, because they can contain secrets.

## Adding a command

1. Add the logic to `cornea.core` as a plain function that returns a value or raises an exception. It must not print or exit.
2. Add a command to `src/cornea/cli/commands.py` that calls it, writes through the consoles in `output.py`, and raises `typer.Exit(code=1)` on failure.
3. Add a `--json` option if the command returns data.
4. Add tests with `typer.testing.CliRunner`, document the command in this file, and regenerate `cli-reference.md`.
