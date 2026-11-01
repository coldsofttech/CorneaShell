# Python API reference

<!-- The reference between the GENERATED markers is written by scripts/gen_api_reference.py from the code. Edit everything else by hand. -->

Public names exported by `cornea`. Install with `pip install cornea-shell`. Everything here can also be done with the [command line](cli-reference.md).

```python
from cornea import Shell, Static, Window

shell = Shell(Static("web/dist"), window=Window(title="My App"))
shell.run()  # opens the window; returns when it is closed
```

The sections below follow the order you usually need them in. The [recipes](#recipes) at the end combine them for common jobs, and the [examples](../examples) folder has a runnable project for each web source.

<!-- BEGIN GENERATED: api -->
## Contents

- **Running the shell:** [`Shell`](#shell), [`run`](#run), [`ready_line`](#ready_line), [`Timings`](#timings)
- **Web sources:** [`WebSource`](#websource), [`Static`](#static), [`Url`](#url), [`Process`](#process), [`Asgi`](#asgi), [`Wsgi`](#wsgi)
- **Settings:** [`Window`](#window), [`Security`](#security), [`DEV_CSP`](#dev_csp), [`Server`](#server), [`Bridge`](#bridge), [`App`](#app)
- **Building blocks:** [`create_app`](#create_app)
- **Logging:** [`configure_logging`](#configure_logging), [`LogLevel`](#loglevel)

## Running the shell

Build a `Shell` and run it, or use `run()` for the short form.

### `Shell`

```python
Shell(
    source: WebSource | str | PathLike[str] | None = None,
    *,
    routers: Iterable[APIRouter] = (),
    security: Security | None = None,
    server: Server | None = None,
    window: Window | None = Window(),
    bridge: Bridge | None = None,
    identity: App | None = None,
    measure: bool | Callable[[Timings], None] = False,
)
```

Runs the web UI on a secured local server.

The server listens on the loopback address by default and picks a free port. The first URL,
`url`, carries a one-time token that is exchanged for a session cookie. With a
`window`, `run` opens a native window on that URL (Windows only, and on the main
thread) and stops the server when the window closes. With `window=None` it only serves, and
the window routes answer from a `cornea.core.window.SimulatedWindow`, so the page can
be tried in a normal browser.

A direct `cornea.core.sources.Url` source is different: the window opens that address
itself and no server is started, so it needs a window with the native frame (the page cannot
reach the window controls) and `url` is the address you gave.

With `measure=True` the start-up time is printed on stderr (and logged) once the first
page has loaded, or once the server answers when there is no window. Pass a function instead
to receive the `Timings` yourself. `timings` has the numbers in either case.

Properties:

- `timings`: How long start-up took so far. See `Timings`.
- `actions`: The native actions the page can call. Register your own with `action`.
- `is_direct`: Whether the window opens a `Url` itself, with no local server.
- `running`: Whether the server is accepting requests.
- `port`: The port the server is bound to. Available after `start`.
- `base_url`: The server's address without the token.
- `url`: The first URL to open: with a token for the local server, or the direct address.

#### `Shell.action`

```python
def Shell.action(
    name: str,
) -> Callable[...]
```

Register a function as a native action: `@shell.action("pick_report")`.

The page calls it with `POST {api_prefix}/bridge/pick_report` and a JSON body of named
arguments; the return value comes back as `{"available": true, "result": ...}`. From
the page, `cornea.call("pick_report", {...})` does the same (see `/api/client.js`).
Actions are Python code, so the command line cannot register them.

**Raises:**

- `ValueError`: If the name is not lowercase words joined by underscores, is a built-in action, or is already registered.

Example:

```pycon
>>> shell = Shell(window=None)
>>> @shell.action("shout")
... def shout(text: str) -> str:
...     return text.upper()
>>> "shout" in shell.actions.names()
True
```

#### `Shell.close_guard`

```python
def Shell.close_guard(
    function: Callable[[], bool],
) -> Callable[...]
```

Hold the window open while `function()` returns true: `@shell.close_guard`.

It is asked whenever the window is about to close, by the close button, Alt+F4 or the
taskbar. When it holds, the window stays and the page gets a `cornea:close-blocked`
event, so it can ask the person. The page then closes with `force`. A function that
raises never holds the window.

Example:

```pycon
>>> shell = Shell(window=None)
>>> export_running = False
>>> @shell.close_guard
... def busy() -> bool:
...     return export_running
>>> busy()
False
```

#### `Shell.notify`

```python
def Shell.notify(
    event: str,
    detail: Any = None,
) -> None
```

Tell the page something happened, as a `cornea:<event>` event on its `window`.

`detail` must be JSON. Without a window this does nothing, and a page that has not
loaded yet does not hear it.

**Raises:**

- `ValueError`: If the event name is not allowed.

Example:

```pycon
>>> shell = Shell(window=None)
>>> shell.notify("export-done", {"rows": 3})  # the page hears "cornea:export-done"
```

#### `Shell.show_notification`

```python
def Shell.show_notification(
    title: str,
    message: str,
    notification_id: str | None = None,
) -> None
```

Show a Windows toast with a plain-text `title` and `message`.

Windows draws it, so its look and place are Windows'. A click brings the window to the
front and sends the page a `cornea:notification-click` event with `notification_id`.
This is always available to your code; `Bridge(notifications=True)` is what lets the
page ask for one.

**Raises:**

- `ValueError`: If the title, message or id is not allowed.
- `RuntimeError`: If there is no window, or the `notifications` extra is missing.

Example:

```pycon
>>> shell = Shell(window=None)
>>> shell.show_notification("Export finished", "3 files were saved.")
Traceback (most recent call last):
...
RuntimeError: There is no window to show a notification from.
```

#### `Shell.start`

```python
def Shell.start() -> Self
```

Bind the port and start serving in a background thread.

Use it (or `with Shell(...)`) when you want the server without `run`, for example
in a test. Call `stop` when you are done.

Example:

```pycon
>>> shell = Shell(window=None).start()
>>> shell.running
True
>>> shell.stop()
```

#### `Shell.stop`

```python
def Shell.stop() -> None
```

Stop serving and release the port. Safe to call more than once.

Example:

```pycon
>>> shell = Shell(window=None).start()
>>> shell.stop()
>>> shell.running
False
```

#### `Shell.run`

```python
def Shell.run(
    on_ready: Callable[['Shell'], None] | None = None,
) -> None
```

Show the window and wait until it closes, or just serve when there is no window.

`on_ready` is called with the shell once it is serving, before the window is shown. Use
it to announce the address, for example with `ready_line`. Serving ends on Ctrl+C
or `stop`. The server is stopped in every case.

**Raises:**

- `RuntimeError`: If the window could not be set up, or WebView2 or pywebview is missing.

Example:

```pycon
>>> shell = Shell(Static("web/dist"), window=Window(title="My App"))
>>> shell.run()  # opens the window; returns when it is closed
>>> shell = Shell(Static("web/dist"), window=None)
>>> shell.run(on_ready=lambda s: print(ready_line(s)))
```

Example:

```pycon
>>> with Shell(window=None) as shell:
...     shell.url.startswith("http://127.0.0.1:")
True
```

### `run`

```python
def run(
    source: WebSource | str | PathLike[str] | None = None,
    *,
    routers: Iterable[APIRouter] = (),
    security: Security | None = None,
    server: Server | None = None,
    window: Window | None = Window(),
    bridge: Bridge | None = None,
    identity: App | None = None,
    measure: bool | Callable[[Timings], None] = False,
    title: str | None = None,
    debug: bool | None = None,
    on_ready: Callable[[Shell], None] | None = None,
) -> None
```

Show the web UI: build a `Shell` and run it until it is closed.

`title` and `debug` are shorthands for the same `window` settings. `on_ready` is
called once the shell is serving; see `Shell.run`. `measure` reports the start-up
time: see `Shell`.

Example:

```pycon
>>> run("web/dist", title="My App")
>>> run(Static("web/dist"), window=Window(frameless=True), measure=True)
```

### `ready_line`

```python
def ready_line(
    shell: Shell,
) -> str
```

A one-line JSON message that says where the UI is, for tools that start the shell.

Example:

```pycon
>>> with Shell(window=None) as shell:
...     json.loads(ready_line(shell))["event"]
'ready'
```

### `Timings`

How long start-up took, in seconds since `Shell.run` (or `start`) began.

A value is `None` when that step did not happen, for example `window_shown` without a
window.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `process_ready` | `float \| None` | `None` | The command of a `Process` source answers. |
| `server_ready` | `float \| None` | `None` | Cornea's own server accepts requests. |
| `window_shown` | `float \| None` | `None` | The native window appears. |
| `page_loaded` | `float \| None` | `None` | The first page has loaded in the window. |

#### `Timings.as_dict`

```python
def Timings.as_dict() -> dict[str, float | None]
```

The steps by name, for JSON.

Example:

```pycon
>>> Timings(server_ready=0.2).as_dict()["server_ready"]
0.2
```

#### `Timings.summary`

```python
def Timings.summary() -> str
```

One line with the steps that happened.

Example:

```pycon
>>> Timings(server_ready=0.2, page_loaded=0.75).summary()
'Start-up: server_ready 0.20 s, page_loaded 0.75 s'
```

Example:

```pycon
>>> Timings(server_ready=0.2).page_loaded is None
True
```

## Web sources

Where the UI comes from. A plain path or address is turned into one of these for you.

### `WebSource`

Base class for everything that can supply the web layer.

### `Static`

A built bundle (React, Vite, Next export, plain HTML) served by the shell.

The bundle folder is found in this order: `path`, then `package_path` inside the installed
`package`, then `web/dist` under the current folder (a source checkout). An explicit
`path` is never replaced by a later place.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `path` | `Path \| str \| None` | `None` | Folder that contains `index.html`. |
| `package` | `str \| None` | `None` | Import name of an installed package that ships the bundle. |
| `package_path` | `str` | `'web/dist'` | Folder inside `package` that contains `index.html`. |
| `spa` | `bool` | `True` | Serve `index.html` for unknown paths without a file extension (client-side routing). |
| `hashed_prefixes` | `tuple[str, ...]` | `('assets/',)` | Folders of fingerprinted files, cached for a year. Everything else is revalidated. |

Properties:

- `directory`: The explicit bundle folder as a `pathlib.Path`, or `None` if not given.

#### `Static.resolve`

```python
def Static.resolve() -> Path
```

Return the absolute bundle folder, or raise if it or its `index.html` is missing.

Example:

```pycon
>>> Static("web/dist").directory.name
'dist'
>>> Static(package="myapp").package_path
'web/dist'
```

### `Url`

A page from a server you already run, such as a dev server.

In `direct` mode the window opens the address itself: the page is not served by Cornea, so it
skips Cornea's security, needs the native window frame and cannot use the window controls.

In `proxy` mode Cornea fetches the pages and serves them from its own address, so they get
Cornea's security, the window controls and the frameless window, and hot reload keeps
working. It needs the `proxy` extra: `pip install "cornea-shell[proxy]"`.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `url` | `str` | `required` | Address of the web UI, for example `http://localhost:5173`. |
| `mode` | `Literal['direct', 'proxy']` | `'direct'` | `direct` opens the address as it is. `proxy` serves it through Cornea. |

Example:

```pycon
>>> Url("http://localhost:5173").mode
'direct'
>>> Url("http://localhost:5173", mode="proxy").mode
'proxy'
```

### `Process`

A dev-server command that Cornea starts for you and stops with the window.

Cornea runs `command`, waits until something listens at `url`, then shows that address
exactly as `Url` does, directly or through the proxy. When Cornea stops, or even if it
crashes, the command and everything it started are stopped too.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `command` | `str \| tuple[str, ...]` | `required` | The command. A string is run by the shell, so `npm run dev` works; a tuple is run as is. |
| `url` | `str` | `required` | Address the command serves on, for example `http://localhost:5173`. |
| `cwd` | `Path \| str \| None` | `None` | Folder to run the command in. |
| `mode` | `Literal['direct', 'proxy']` | `'direct'` | As for `Url`: `direct` opens the address, `proxy` serves it through Cornea. |
| `timeout` | `float` | `30.0` | Seconds to wait for the address to answer before giving up. |

Example:

```pycon
>>> Process("npm run dev", url="http://localhost:5173").command
'npm run dev'
```

### `Asgi`

An ASGI app (FastAPI, Django ASGI) mounted in-process on the shell's port.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `target` | `str \| Callable[...]` | `required` | `module:attribute` import string, or the app itself. |
| `app_dir` | `Path \| str \| None` | `None` | Folder added to `sys.path` before importing, for example the project root. |

#### `Asgi.load`

```python
def Asgi.load() -> Callable[...]
```

Import the app if needed and return it.

Example:

```pycon
>>> Asgi("myproject.asgi:application", app_dir=".").target
'myproject.asgi:application'
```

### `Wsgi`

A WSGI app (Flask, Django WSGI) adapted to ASGI and mounted in-process.

Needs the `wsgi` extra: `pip install cornea-shell[wsgi]`.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `target` | `str \| Callable[...]` | `required` | `module:attribute` import string, or the app itself. |
| `app_dir` | `Path \| str \| None` | `None` | Folder added to `sys.path` before importing, for example the project root. |

#### `Wsgi.load`

```python
def Wsgi.load() -> Callable[...]
```

Import the app if needed and return it wrapped as an ASGI app.

Example:

```pycon
>>> Wsgi("myapp:app").target
'myapp:app'
```

## Settings

Frozen dataclasses. Each one validates its values when you create it.

### `Window`

Native window options. The context menu and developer tools are off unless enabled.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `title` | `str` | `'Cornea Shell'` | Window title. |
| `size` | `tuple[int, int]` | `(1024, 768)` | Initial width and height in pixels. |
| `min_size` | `tuple[int, int]` | `(400, 300)` | Smallest width and height the user can resize to. |
| `position` | `tuple[int, int] \| None` | `None` | Top-left corner on screen; `None` lets the system place the window. |
| `frameless` | `bool` | `False` | Hide the native title bar; the web UI draws its own. |
| `resizable` | `bool` | `True` | Let the user resize the window. |
| `on_top` | `bool` | `False` | Keep the window above other windows. |
| `context_menu` | `bool` | `False` | Enable the right-click menu. Off by default. |
| `devtools` | `bool` | `False` | Enable the developer tools. Off by default. |
| `debug` | `bool` | `False` | Debug mode turns on the context menu and developer tools. |
| `icon` | `Path \| str \| None` | `None` | Icon for the window and its taskbar button: an `.ico` file or an image (`.png`, `.bmp`, `.gif`, `.jpg`). A relative path is relative to the current folder. |
| `downloads` | `bool` | `False` | Let the page download files. The person chooses where to save each one in a native dialog. Off by default, so a page cannot put files on disk. |
| `drop_files` | `bool` | `False` | Tell the page which files were dropped on the window, with their full paths, as a `cornea:drop` event. Off by default, because a full path says where a person keeps things. |
| `js_api` | `bool` | `False` | Give the page `window.pywebview.api`: the window controls and the native actions. It lets a frameless window show an address that Cornea does not serve. Every page that loads in the window gets these powers, so use it only for pages you trust. |

Properties:

- `context_menu_enabled`: Whether the right-click menu is available.
- `devtools_enabled`: Whether the developer tools can be opened.

Example:

```pycon
>>> Window(title="My App", frameless=True).title
'My App'
>>> Window().devtools_enabled
False
>>> Window(debug=True).devtools_enabled
True
```

### `Security`

Local server protections. The defaults are the strict ones.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `allowed_hosts` | `tuple[str, ...]` | `()` | Extra `Host` values to accept. The bound `127.0.0.1:<port>` is always allowed. |
| `csp` | `str` | `"default-src 'self'; script-src 'self';…` | `Content-Security-Policy` value. Relax it explicitly, for example `style-src`. |
| `api_prefix` | `str` | `'/api'` | Path prefix the host app's routers are mounted under. |
| `token_ttl` | `float` | `60.0` | Seconds the one-time bootstrap token stays valid. |
| `cookie_samesite` | `Literal['strict', 'lax']` | `'strict'` | `SameSite` attribute of the session cookie. |
| `public_paths` | `tuple[str, ...]` | `('/health',)` | Paths reachable without a session. An entry ending in `/` matches everything below it. |
| `require_origin` | `bool` | `True` | Reject POST, PUT, PATCH and DELETE requests that send no `Origin` header. |

Example:

```pycon
>>> Security(allowed_hosts=("App.Local",)).allowed_hosts
('app.local',)
>>> Security(csp="default-src 'self'; style-src 'self' 'unsafe-inline'").csp
"default-src 'self'; style-src 'self' 'unsafe-inline'"
```

### `DEV_CSP`

The default policy plus inline scripts and styles, which development servers such as Vite inject for hot reload. Nothing else is loosened. It is for development only and is never the default. Use it with `Security(csp=DEV_CSP)` or `--csp-profile dev`.

```text
default-src 'self';
script-src 'self' 'unsafe-inline';
style-src 'self' 'unsafe-inline';
img-src 'self' data:;
connect-src 'self';
object-src 'none';
base-uri 'none';
frame-ancestors 'none';
form-action 'self'
```

### `Server`

Where the local server listens. Port 0 picks a free port.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `host` | `str` | `'127.0.0.1'` | Address to bind. Keep the loopback default unless the server must be reachable elsewhere. |
| `port` | `int` | `0` | Port to bind. `0` picks a free port. |

Example:

```pycon
>>> Server(port=8080)
Server(host='127.0.0.1', port=8080)
```

### `Bridge`

Which built-in native actions the page may call. All of them are on by default.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `disabled` | `tuple[str, ...]` | `()` | Built-in actions to switch off. A disabled action answers like an unknown one. |
| `notifications` | `bool` | `False` | Add the `show_notification` action, which shows a Windows toast. Off by default, so a page cannot raise alerts unless you allow it. Needs the `notifications` extra. |
| `open_files` | `bool` | `False` | Add the `open_file` and `reveal` actions, which open a file in the program Windows has for it and show a file in Explorer. Off by default. A page can name any path, so `open_file` still refuses programs, scripts and shortcuts, network paths and missing files. |

Example:

```pycon
>>> Bridge(disabled=("open_external",)).disabled
('open_external',)
```

### `App`

Who the app is, for the things that must tell one app from another.

The id names the app's data folder, the Windows taskbar identity (so its icon is not grouped
under `python.exe`) and the single-instance lock. Several copies run independently unless
`single_instance` is on.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `id` | `str \| None` | `None` | A short name such as `com.example.notes`: letters, digits, dots, dashes, underscores. |
| `single_instance` | `bool` | `False` | Allow one copy at a time: starting a second one brings the first window to the front. |
| `remember_window` | `bool` | `False` | Reopen the window where it was and at the size it had. |

Example:

```pycon
>>> App(id="com.example.notes", remember_window=True).remember_window
True
```

## Building blocks

For tests and for mounting Cornea in a larger program.

### `create_app`

```python
def create_app(
    source: WebSource | str | PathLike[str] | None = None,
    *,
    routers: Iterable[APIRouter] = (),
    security: Security | None = None,
    bridge: Bridge | None = None,
    bootstrap_token: str | None = None,
    app_id: str | None = None,
) -> FastAPI
```

Build the FastAPI app that the shell serves.

`source` is where the UI comes from; `None` gives an API-only app. The host's
`routers` are mounted under `security.api_prefix`. The shell's own routes (the API
prefix and `/health`) always win over the source. The bootstrap token and the
allowed-host set are on `app.state` for the shell; add the bound address with
`AppFactory.allow_host` once the port is known. `app_id` is part of the session
cookie's name.

Example:

```pycon
>>> app = create_app()
>>> app.state.security.api_prefix
'/api'
```

## Logging

Cornea is quiet until you ask. It logs to the `cornea` logger.

### `configure_logging`

```python
def configure_logging(
    level: Literal['debug', 'info', 'warning', 'error'] = 'debug',
    *,
    file: Path | str | None = None,
) -> None
```

Show Cornea's log messages on stderr, and optionally write all of them to a file.

`level` is the least important message shown on stderr. The file always gets every
message, down to `debug`, so it is the one to attach to a bug report. Calling this again
replaces the earlier setup. Start-up tokens are never written.

**Raises:**

- `ValueError`: If `level` is not one of `LOG_LEVELS`.
- `OSError`: If the file cannot be opened.

### `LogLevel`

```python
def LogLevel(
    *args,
    **kwargs,
)
```
<!-- END GENERATED -->

## Recipes

Short, complete snippets for common jobs. Each one has a runnable project in [examples](../examples). Paths are relative to where you run the program.

### Show a folder of built files

```python
from cornea import Shell, Static, Window

Shell(Static("web/dist"), window=Window(title="My App", size=(1200, 800))).run()
```

`Static` serves the folder as it is and falls back to `index.html` for page routes, so a client-side router works. Files under `assets/` are cached for a year. `run("web/dist", title="My App")` is the one-line form.

### Add your own routes and actions

Routes are ordinary FastAPI routers, mounted under `/api` behind the session cookie. Actions are Python functions the page can call.

```python
from fastapi import APIRouter
from cornea import Shell, Static

router = APIRouter()


@router.get("/greeting")
def greeting(name: str = "world") -> dict[str, str]:
    return {"message": f"Hello, {name}!"}


shell = Shell(Static("web/dist"), routers=[router])


@shell.action("shout")
def shout(text: str) -> str:
    return text.upper()


shell.run()
```

```javascript
await fetch("/api/greeting?name=Ada");                      // the route
await cornea.call("shout", { text: "hello" });              // the action (needs /api/client.js)
```

### Mount a Python web app

```python
from cornea import Asgi, Shell, Wsgi

Shell(Asgi("main:app", app_dir="examples/fastapi_app")).run()  # FastAPI, Django ASGI
Shell(
    Wsgi("flask_example:app", app_dir="examples/flask_app")
).run()  # Flask, Django WSGI (needs the wsgi extra)
```

`/api` and `/health` always belong to Cornea; your routes can be anywhere else.

### Run a dev server with hot reload

```python
from cornea import DEV_CSP, Process, Security, Shell

source = Process(
    "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
    url="http://127.0.0.1:5173",
    cwd="web",
    mode="proxy",  # Cornea serves the page, so it gets the security layer and the window controls
)
Shell(source, security=Security(csp=DEV_CSP)).run()  # dev servers inject inline scripts
```

Cornea starts the command, waits for the address, and stops the command and everything it started when the window closes. Proxy mode needs the `proxy` extra.

### Let the page show notifications, open files and accept drops

These are all off by default.

```python
from cornea import Bridge, Shell, Static, Window

shell = Shell(
    Static("web/dist"),
    bridge=Bridge(notifications=True, open_files=True),
    window=Window(drop_files=True, downloads=True),
)
shell.show_notification("Export finished", "3 files were saved.", notification_id="export-1")
shell.run()
```

The page calls `cornea.call("show_notification", {...})`, `cornea.call("open_file", {"path": ...})`, and listens for `cornea:drop` and `cornea:notification-click`. Notifications need the `notifications` extra.

### Tell the page something, and keep the window open while busy

```python
from cornea import Shell, Static

shell = Shell(Static("web/dist"))
export_running = False


@shell.close_guard
def busy() -> bool:
    return export_running  # True keeps the window open


shell.notify("export-done", {"rows": 3})  # the page gets a "cornea:export-done" event
```

### One copy at a time, and a remembered window

```python
from cornea import App, Shell, Static, Window

Shell(
    Static("web/dist"),
    window=Window(title="Notes", icon="icon.png"),
    identity=App(id="com.example.notes", single_instance=True, remember_window=True),
).run()
```

A second start brings the first window to the front. The window comes back at its last size and place. The app keeps its files in `%LOCALAPPDATA%\Cornea\com.example.notes\`.

### Serve without a window, or test your app

```python
import json
from cornea import Shell, Static, ready_line

with Shell(Static("web/dist"), window=None) as shell:
    print(ready_line(shell))  # {"event": "ready", "url": "...", ...}
    print(json.loads(ready_line(shell))["port"])
```

With `window=None` the shell only serves, so you can open the printed address in a browser or drive it from a test. `Shell.start()` and `Shell.stop()` do the same without a `with` block.

### Turn on logging and measure start-up

```python
from cornea import Shell, Static, Window, configure_logging

configure_logging("debug", file="cornea.log")  # screen at "debug", the file gets everything
Shell(Static("web/dist"), window=Window(debug=True), measure=True).run()
```

`measure=True` prints how long start-up took once the first page has loaded; pass a function instead to receive the `Timings` yourself. `Window(debug=True)` also turns on the right-click menu and developer tools.
