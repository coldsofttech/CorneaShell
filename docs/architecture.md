# Architecture

How Cornea Shell works, for people who change it or build on it. For day-to-day commands see [development](development.md). For what each option does see the [command line guide](cli.md) and the [Python API reference](api-reference.md).

## Overview

One process does everything. A background thread runs a small web server on the loopback address; the main thread runs the window.

```text
 native window (pywebview, WebView2)      browser tab (cornea serve)
                 \                              /
                  +---- http://127.0.0.1:<port> ----+
                                 |
                      SecurityMiddleware      host, origin, token, session, headers
                                 |
                          FastAPI app
        /health | /api/window | /api/bridge | your routers | rest of /api -> 404
                                 |
                      the web source at "/"
        Static bundle | ASGI app | WSGI app (adapted) | proxy to another server
```

A direct `Url` source skips all of this: no server is started and the window opens the address itself. A proxied one (`Url(..., mode="proxy")`) is served like any other source, by forwarding to the other server.

## Source layout

```text
src/cornea/__init__.py       public API (everything in __all__)
src/cornea/core/config.py    Server, Security, Bridge and Window settings (frozen dataclasses)
src/cornea/core/sources.py   Static, Url, Asgi, Wsgi and the shorthand rules
src/cornea/core/security.py  the ASGI middleware and the one-time-token session gate
src/cornea/core/static.py    bundle serving: page fallback, caching, content types
src/cornea/core/proxy.py     the reverse proxy for another server's pages (optional `proxy` extra)
src/cornea/core/app.py       create_app(): puts the pieces above into one FastAPI app
src/cornea/core/shell.py     Shell and run(): the server thread, the window, shutdown
src/cornea/core/process.py   starts a dev-server command and stops it with everything it started
src/cornea/core/appdata.py   the per-app data folder
src/cornea/core/window_memory.py   remembered window size and position
src/cornea/core/single_instance.py one copy at a time, and waking the first copy
src/cornea/core/window_api.py      the opt-in js_api object
src/cornea/core/logs.py      configure_logging(): stderr and file handlers, token redaction
src/cornea/core/close_guard.py     holds the window open while the app is busy
src/cornea/core/notifications.py   Windows toast notifications through the winrt bindings
src/cornea/core/window.py    pywebview window, window controller, environment checks
src/cornea/core/window_routes.py   /api/window routes
src/cornea/core/bridge.py    native actions and the action registry
src/cornea/core/bridge_routes.py   /api/bridge route
src/cornea/cli/              the cornea command: a thin wrapper over run()
src/cornea/cli/config.py     cornea.toml and [tool.cornea]: defaults for the command
src/cornea/core/environment.py   versions and places, for `cornea info` and the debug log
tests/                       unit tests; tests/integration/ runs real processes and a real window
examples/                    runnable example projects
```

The command line never does anything the Python API cannot. Each setting has exactly one flag, and a test fails when a setting is added without one.

## Start-up and shutdown

`Shell.run()` does this in order:

1. If there is a window, check Windows, the WebView2 runtime and pywebview. Nothing has been started yet, so a failure leaves nothing behind.
2. Bind a loopback socket on a free port, add the bound `host:port` to the allowed hosts, and start uvicorn on that socket in a background thread. Binding first removes the race between choosing a port and using it.
3. Call `on_ready` with the shell, so a caller can announce the address (`ready_line()` builds the JSON line that `cornea serve` prints).
4. With a window, create it on the first URL, which carries the one-time token, and run its event loop on the main thread. Without one, wait for Ctrl+C or `stop()`.
5. Stop the server and close the socket in every case, so the port is released.

The access log is off. It would print the request line of the first URL, which contains the token.

## Security model

All of it lives in one ASGI middleware, so it guards a mounted Flask or Django app as well as FastAPI routes. Each request, in order:

1. **Host.** The `Host` header must be on the allow-list: the bound `127.0.0.1:<port>` plus any `allowed_hosts`. This stops DNS-rebinding attacks.
2. **Origin.** `POST`, `PUT`, `PATCH` and `DELETE` must carry an `Origin` that matches an allowed host. A missing one is refused unless `require_origin` is turned off. WebSocket handshakes get the same check.
3. **Start-up token.** `?cornea_token=<token>` on a `GET` is exchanged for a session. The token is single use, compared in constant time, and expires after `token_ttl` seconds. The answer is a `303` to the same path without the token, with an `HttpOnly`, `SameSite=Strict` session cookie that lasts until the window closes. The parameter has a long name on purpose: a short one such as `t` collides with what other apps use (Vite adds `?t=<timestamp>` to hot-reloaded files).
4. **Session.** Every other request needs that cookie, except the `public_paths` (default `/health`).
5. **Headers** on every response, including the refusals: a strict `Content-Security-Policy` (an app's own policy is kept), `X-Content-Type-Options`, `Referrer-Policy`, and the cross-origin opener and resource policies. API responses are `no-store`.

What it does not cover: a direct `Url` is not served by Cornea, and with `js_api` every page the window loads gets the window controls and the native actions (see [js_api](#js_api-and-its-risk)); the code of your own routes and actions runs with your permissions; and a local program that can read your terminal can read the printed address of `cornea serve` while the token is still valid.

## Sources and who wins a path

Routes are registered in this order, and the first match wins:

1. `/health`
2. `{api_prefix}/window` and `{api_prefix}/bridge` (Cornea's own)
3. your routers, under `{api_prefix}`
4. a catch-all for the rest of `{api_prefix}`, which answers a JSON 404
5. the source, mounted at `/`

So a mounted app can never shadow `/api`, `/health`, the window controls or the bridge. Static bundles get single-page-app routing (a path without a file extension falls back to `index.html`), a one-year cache for files under `assets/`, `no-cache` for the rest, and content types set by Cornea itself, because a Windows registry can call `.js` plain text.

## Proxying another server

`ProxyApp` forwards HTTP and WebSocket traffic to a fixed upstream address, so the page is served from Cornea's own address and goes through the same security layer. The upstream address comes from configuration and is never read from a request. What it changes on the way:

- **Cornea's session cookie is removed** from the `Cookie` header, so the upstream never sees it. Other cookies pass through, and `Domain=` is dropped from the cookies the upstream sets, since the browser only knows Cornea's address.
- **`Host`, `Origin` and `Referer`** are rewritten to the upstream's own, so a dev server's host check or an app's CSRF check accepts the request.
- **Redirects** to the upstream's address become relative, and are passed on rather than followed.
- **Bodies are streamed** in both directions and stay compressed as the client asked, so event streams and large uploads are not buffered. The upstream's `Date` and `Server` headers are dropped, because Cornea's server adds its own.
- **WebSockets** (hot reload) are accepted, connected to the upstream with the same sub-protocols, and pumped both ways. A refused or unreachable upstream closes the socket.
- **Proxy settings in the environment are ignored**, so a corporate proxy cannot catch local traffic. An unreachable upstream answers a 502 page that names it.

The default content security policy blocks the inline scripts and styles that dev servers inject. `DEV_CSP` (`--csp-profile dev`) adds exactly those two permissions and changes nothing else. It is for development only.

## The window and the bridge

pywebview ties the context menu, developer tools, shortcut keys and status bar to one debug switch. Cornea starts in debug mode when any of them is wanted and then sets each WebView2 option to exactly what the `Window` settings ask for; if that fails the window closes rather than leave tools on. The window is private (nothing survives a restart) and pywebview needs the main thread, so `run()` with a window must be called from it.

Window controls (`minimize`, `maximize`, `restore`, `close`, title and state) are routes, not a JavaScript object, so any page can use them with `fetch()` and the same page works in a browser. Without a window a stand-in answers them.

The bridge is one route, `POST {api_prefix}/bridge/{action}`. Built-in actions are choose folder, choose file, choose save path, open an `http`, `https` or `mailto` link, and platform info. Your own actions are registered with `@shell.action`. Unknown and switched-off actions answer 404, bad arguments 422, and a crash in an action is logged and answered with a generic 500, so details never reach the page.

## The Process runner

`Process(command, url, ...)` is a source that starts a dev server and then behaves like a `Url`, direct or proxied. `process.py` does the work:

1. Refuse to start if something already answers on the address, so Cornea never shows (and later stops) a server it did not start.
2. Start the command. A string runs through the shell, so `npm run dev` works; a tuple runs as given.
3. Poll the address until it accepts a connection, within `timeout`. While waiting, watch the command: if it exits first, the error carries its last lines of output.
4. On shutdown, stop the command and everything it started.

The failures are: the command exited early, the address did not answer in time, the address is already in use, or the program could not be started. The command line prints them as one line and exits with code 1.

`npm run dev` starts `node` as a child, so stopping only `npm` would leave the server running. On Windows the command therefore runs inside a job object that is set to kill its members when the last handle closes. Stopping closes the job. If Cornea crashes, the system closes its handles, which closes the job and ends the whole tree, so a crash does not leave a dev server behind either.

## The app identity

`App(id, single_instance, remember_window)` is passed to `Shell` as `identity=` (`app` is already the FastAPI app). The two options need an id.

- **Data folder.** `%LOCALAPPDATA%\Cornea\<id>\` holds `window.json` (the remembered window) and `instance.json` (while the app runs).
- **Remembered window.** Size, position and the maximized state are saved when the window closes and used at the next start. The size never goes below the minimum. A position is kept only if the window's top-left corner would still be on a screen; otherwise it is dropped and the system places the window, which handles an unplugged monitor.
- **Single instance.** The first copy takes a named Windows mutex, so the system releases the lock if the app crashes and no stale lock can exist. It also listens on a private loopback port and writes that port and a random secret to `instance.json`. A second copy fails to get the mutex, reads the file, and sends the secret to that port. The first copy checks the secret, restores and activates its window, and the second exits (`AlreadyRunning`, with `.activated` telling whether the first copy answered). A request without the secret is ignored. Single instance needs a window.
- **Taskbar identity.** The id is set as the Windows app identity, so the taskbar does not group the window under `python.exe`.

## js_api and its risk

A directly opened address is not served by Cornea, so its page cannot call the window routes, and a frameless window would have no way to close. `Window(js_api=True)` offers another way: pywebview puts a `window.pywebview.api` object into the page with `minimize()`, `maximize()`, `restore()`, `close()`, `set_title(title)`, `state()`, `actions()` and `call_action(action, parameters)`. `call_action` returns the same shape as the HTTP bridge route.

It is off by default, and the rule that a directly opened address cannot be frameless holds unless it is on. The risk is the one the object brings: pywebview adds it to every page that loads in the window, including one the window navigates to. That page gets the window controls and the native actions (dialogs, opening a link, platform information). Use it only for pages you trust. Single actions can still be switched off with `--disable-action`. Proxy mode needs none of this: the page is served by Cornea and uses the HTTP routes behind the session.

pywebview builds the JavaScript functions from the Python parameter names, and a parameter called `arguments` breaks them. That is why the second parameter of `call_action` is `parameters`. The object keeps its fields private, because pywebview exposes every public attribute it holds.

## Startup time

`Shell.timings` returns a `Timings` with `process_ready`, `server_ready`, `window_shown` and `page_loaded`, in seconds since `run()` (or `start()`) began. A step that did not happen is `None`. `Timings.as_dict()` and `Timings.summary()` give the numbers as JSON-ready data and as one line.

`Shell(measure=True)` and `run(measure=True)` report the timings once, when the last step has finished: `page_loaded` with a window, `server_ready` without one. The default report is the summary line on stderr plus an `info` log message. Pass a function instead (`measure=callback`) to receive the `Timings` yourself. The command line uses this: `--measure` shows a Rich table, `--json-friendly` prints the JSON line and `--json-file` writes it. Because the measuring is part of the package, it works for any app, not just the examples. To compare runs, start the app several times with `--measure --json-file` and look at the median.

Medians from 7 runs on the development machine (Windows 11, Python 3.11), measured with `--measure`:

| Step | Median |
| --- | --- |
| Import the package | 0.24 s |
| Server accepting requests | 0.05 s |
| Window shown | 0.41 s |
| First page loaded | 0.70 s |

The target, with about three times the margin for slower machines, counted from the start of `run()` and leaving out the import (about 0.4 s on a slower machine):

| Step | Target |
| --- | --- |
| Server accepting requests | under 0.5 s |
| Window shown | under 2 s |
| First page loaded | under 3 s |

The target is a guide, not a test. A test that fails on speed would be flaky on shared CI machines, so nothing enforces it; run your app with `--measure` to check.

## Telling the page, and the close guard

`Shell.notify(event, detail)` sends a DOM `CustomEvent` named `cornea:<event>` on the page's `window`, using pywebview's `evaluate_js`. The detail is JSON-encoded, never concatenated into the script, and event names are limited to lowercase words so a name cannot carry code. Without a window it does nothing. A page that has not loaded yet misses the event.

The close guard (`close_guard.py`) answers one question: should closing be held back now? It holds if the page switched it on (`POST /api/window/close-guard`) or if any function registered with `@shell.close_guard` returns true. A guard that raises is logged and never holds, so a buggy app can still be closed. `NativeWindow` asks it in two places: `close()` (the close route and `js_api`) and pywebview's `closing` event, which covers Alt+F4 and the taskbar. When it holds, the window stays and the page gets `cornea:close-blocked`. `close(force=True)` skips the guard, which is how the page closes after the person confirms.

Dropped files use pywebview's DOM events. They are installed once, after the first page load, only when `Window(drop_files=True)`. The event carries paths only, never contents, and only for files a person dropped.

`open_file` and `reveal` are built-in actions that exist only with `Bridge(open_files=True)`. `open_file` resolves the path, refuses network paths (a link to a share would leak the Windows login to it), folders, missing files, files without an extension and the types in `BLOCKED_SUFFIXES` (programs, scripts, shortcuts), and then calls `os.startfile`. `reveal` runs `explorer` with the path as one argument; it is allowed for any existing path because showing a file does not run it. Page and line hints, as VethuQ passes to its PDF viewer, are not supported: they need a program-specific command line.

## Notifications

`show_notification` is a built-in action that exists only with `Bridge(notifications=True)`; `Shell.show_notification()` is always available to the host. Both go through `Notifier` (`notifications.py`), which uses the optional `winrt` packages (the `notifications` extra), imported only when a toast is shown so the package imports without them. A missing extra or a non-Windows system answers like a missing window: `available: false` for the page, `RuntimeError` for Python.

The text is limited (title 64, message 256 characters), plain, and XML-escaped when the toast is built, so it cannot add markup, buttons or images. A toast needs an app identity to show a name and icon. `Notifier` registers one for the current user under `HKEY_CURRENT_USER\Software\Classes\AppUserModelId\<id>` with a `DisplayName` (the window title) and an `IconUri` (the window icon). It uses `App(id=...)`, or `Cornea.Shell` when there is none. No Start-menu shortcut is made. The key is left in place; removing it is harmless.

Windows calls back on a thread of its own when a toast is clicked, dismissed or fails. Live toasts are kept in a set until then, because a toast that is freed early never calls back. A click activates the window and sends the page `cornea:notification-click` with the `notification_id`. Click callbacks for unpackaged apps depend on Windows delivering the event to the running process; this was not tested with a real click.

## Logging

Every module logs to a child of the `cornea` logger, and Cornea never configures logging itself, so a program that sets up logging sees these messages like any library's. `configure_logging(level, file=...)` is the quick way: it adds a stderr handler at `level` and, with a file, a file handler that always records `debug`. The `cornea` command calls it for `--log-level`, `--log-file` and `--debug`.

Debug mode (`Window(debug=True)`, which `Shell.run()` checks, or `--debug`) calls `enable_debug_logging()`. It does nothing if the `cornea` logger or the root logger already has a handler, because the program chose where logs go. Otherwise it logs at `debug` to stderr and to `cornea.log` in `%LOCALAPPDATA%\Cornea\logs` (`appdata.logs_dir()`), which does not depend on where the program was started. If the file cannot be opened it logs to stderr only. Files rotate at 1 MB and keep three backups. The first lines of a debug log are `environment_details()` (the versions, the WebView2 runtime and the log folder) and the window, server, security and app settings; none of them holds a secret.

What is logged, all at `debug`: start-up and shutdown steps with their timings, requests the security layer refused (method, path and reason), proxy failures, native action names and outcomes, and the dev-server command's output lines. Query strings, cookies, action arguments and results are never logged, and a formatter hides anything that looks like `cornea_token=...` as a last line of defence, tracebacks included. The default is quiet because most messages are only useful when something is wrong.

## The settings file

`cli/config.py` finds `cornea.toml` (or `[tool.cornea]`) from the current folder upward and turns it into Click's `default_map` for `open` and `serve`. Because it is a default map, a flag always wins and no merging code is needed. The one special case is the source: if the command line names a source, `_source_arguments()` clears the source values that came from the file, so a `run` from the file cannot combine with a folder from the command line. Unknown tables and keys are errors, so a typo is never silently ignored. The Python API does not read the file.

## Testing

- **Unit tests** run every module against a real server on a free port where the server matters, and against a fake pywebview where a window would be needed. Coverage must stay above the minimum in `pyproject.toml`.
- **Example tests** start each project in `examples/` for real, without a window.
- **Integration tests** (`pytest -m integration`) run `cornea serve` as its own process and open a real window. The window test skips itself without WebView2.

## Not yet

Other platforms are not supported.
