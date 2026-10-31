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
        Static bundle | ASGI app | WSGI app (adapted) | nothing (direct address)
```

A direct `Url` source skips all of this: no server is started and the window opens the address itself.

## Source layout

```text
src/cornea/__init__.py       public API (everything in __all__)
src/cornea/core/config.py    Server, Security, Bridge and Window settings (frozen dataclasses)
src/cornea/core/sources.py   Static, Url, Asgi, Wsgi and the shorthand rules
src/cornea/core/security.py  the ASGI middleware and the one-time-token session gate
src/cornea/core/static.py    bundle serving: page fallback, caching, content types
src/cornea/core/app.py       create_app(): puts the pieces above into one FastAPI app
src/cornea/core/shell.py     Shell and run(): the server thread, the window, shutdown
src/cornea/core/window.py    pywebview window, window controller, environment checks
src/cornea/core/window_routes.py   /api/window routes
src/cornea/core/bridge.py    native actions and the action registry
src/cornea/core/bridge_routes.py   /api/bridge route
src/cornea/cli/              the cornea command: a thin wrapper over run()
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
3. **Start-up token.** `?t=<token>` on a `GET` is exchanged for a session. The token is single use, compared in constant time, and expires after `token_ttl` seconds. The answer is a `303` to the same path without the token, with an `HttpOnly`, `SameSite=Strict` session cookie that lasts until the window closes.
4. **Session.** Every other request needs that cookie, except the `public_paths` (default `/health`).
5. **Headers** on every response, including the refusals: a strict `Content-Security-Policy` (an app's own policy is kept), `X-Content-Type-Options`, `Referrer-Policy`, and the cross-origin opener and resource policies. API responses are `no-store`.

What it does not cover: a direct `Url` is not served by Cornea; the code of your own routes and actions runs with your permissions; and a local program that can read your terminal can read the printed address of `cornea serve` while the token is still valid.

## Sources and who wins a path

Routes are registered in this order, and the first match wins:

1. `/health`
2. `{api_prefix}/window` and `{api_prefix}/bridge` (Cornea's own)
3. your routers, under `{api_prefix}`
4. a catch-all for the rest of `{api_prefix}`, which answers a JSON 404
5. the source, mounted at `/`

So a mounted app can never shadow `/api`, `/health`, the window controls or the bridge. Static bundles get single-page-app routing (a path without a file extension falls back to `index.html`), a one-year cache for files under `assets/`, `no-cache` for the rest, and content types set by Cornea itself, because a Windows registry can call `.js` plain text.

## The window and the bridge

pywebview ties the context menu, developer tools, shortcut keys and status bar to one debug switch. Cornea starts in debug mode when any of them is wanted and then sets each WebView2 option to exactly what the `Window` settings ask for; if that fails the window closes rather than leave tools on. The window is private (nothing survives a restart) and pywebview needs the main thread, so `run()` with a window must be called from it.

Window controls (`minimize`, `maximize`, `restore`, `close`, title and state) are routes, not a JavaScript object, so any page can use them with `fetch()` and the same page works in a browser. Without a window a stand-in answers them.

The bridge is one route, `POST {api_prefix}/bridge/{action}`. Built-in actions are choose folder, choose file, choose save path, open an `http`, `https` or `mailto` link, and platform info. Your own actions are registered with `@shell.action`. Unknown and switched-off actions answer 404, bad arguments 422, and a crash in an action is logged and answered with a generic 500, so details never reach the page.

## Testing

- **Unit tests** run every module against a real server on a free port where the server matters, and against a fake pywebview where a window would be needed. Coverage must stay above the minimum in `pyproject.toml`.
- **Example tests** start each project in `examples/` for real, without a window.
- **Integration tests** (`pytest -m integration`) run `cornea serve` as its own process and open a real window. The window test skips itself without WebView2.

## Not yet

Proxy mode (serving another server's pages through Cornea so its security and window controls apply) and a source that starts a dev-server command for you are planned for 0.2. Other platforms are not supported.
