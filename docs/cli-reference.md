# `cornea`

Host a web UI in a native window with a secured local server.

**Usage**:

```console
$ cornea [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `-V, --version`: Show the version and exit.
* `-v, --verbose`: Show extra detail.
* `-q, --quiet`: Only show errors.
* `--no-color`: Disable colored output.
* `--help`: Show this message and exit.

**Commands**:

* `info`: Show version and environment details.
* `open`: Show the web UI in a native window (Windows).
* `serve`: Serve the web UI without a window, for a...

## `cornea info`

Show version and environment details.

**Usage**:

```console
$ cornea info [OPTIONS]
```

**Options**:

* `--json`: Output as JSON.
* `--help`: Show this message and exit.

## `cornea open`

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
* `--title <str>`: Window title.
* `--size <str>`: Window size, like 1200x800.
* `--min-size <str>`: Smallest window size, like 400x300.
* `--position <str>`: Window position on screen, like 100,50.
* `--frameless`: Hide the native title bar; the page draws its own.
* `--resizable / --no-resizable`: Let the user resize (default on).
* `--on-top`: Keep the window on top.
* `--context-menu`: Allow the right-click menu.
* `--devtools`: Allow the developer tools.
* `--debug`: Turn on the context menu and developer tools.
* `--help`: Show this message and exit.

## `cornea serve`

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
* `--help`: Show this message and exit.

## Examples

### `cornea`

```console
$ cornea --version
$ cornea --quiet info
$ cornea --no-color info
```

### `cornea info`

```console
$ cornea info
$ cornea info --json
```

### `cornea open`

```console
$ cornea open web/dist
$ cornea open web/dist --title "My App" --size 1200x800 --frameless --debug
$ cornea open http://localhost:5173 --size 1280x800
$ cornea open http://localhost:5173 --mode proxy --csp-profile dev --frameless
```

### `cornea serve`

```console
$ cornea serve web/dist
$ cornea serve --asgi myproject.asgi:application --app-dir .
$ cornea serve web/dist --port 8765 --public-path /health --public-path /status
$ cornea serve http://localhost:5173 --mode proxy --csp-profile dev
```
