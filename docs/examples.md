# Example entry points

Each folder in `examples/` has a `main.py` that builds a `Shell` in `build_shell(...)` and runs it in `main()`. Tests load these files and call `build_shell(headless=True)`.

| Example | Source | Notes |
| --- | --- | --- |
| static_html | `Static(HERE)` | Frameless, `icon="icon.png"`; `--remember` adds `App(id=..., remember_window=True)` |
| react_vite | `Static(dist)` or `Process("npm run dev ...", mode="proxy")` | `--dev` needs `Security(csp=DEV_CSP)`; built mode exits with a hint when `dist/` is missing |
| fastapi_app | `Static` plus routers, or `Asgi("main:app")` with `--mount` | When mounted, `/api` still belongs to Cornea, so the app serves `/greeting` and the page reads the URL from a `<meta>` tag |
| flask_app | `Wsgi("flask_example:app")` | |
| django_app | `Asgi("django_example:application")` | |
| node_server | `Process(("node", "server.js", port))` or `Url(...)` with `--external` | `server.js` takes the port as an argument; a direct address needs a window, so `--headless` needs `--mode proxy` |

Headless runs pass `window=None` and print `ready_line(shell)` from `on_ready`.

## Servers started by a command

| Example | Command Cornea runs | Notes |
| --- | --- | --- |
| vue_vite | `Static(dist)` or `Process("npm run dev ...", mode="proxy")` | Same as react_vite; `--dev` needs `DEV_CSP` |
| htmx_fastapi | `Asgi("main:app")` | htmx is vendored; strict policy, no inline script or style |
| streamlit_app | `python -m streamlit run app.py --server.port N ...` | Proxy plus `DEV_CSP`; the WebSocket handshake works with Streamlit's default origin checks |
| mkdocs_site | `python -m mkdocs serve -a 127.0.0.1:N` (`--live`), or `Static(site)` after `mkdocs build` | Live uses a WebSocket and `DEV_CSP` |
| dotnet_server | `dotnet run --project DIR --urls http://127.0.0.1:N` | Timeout 120 s for the first compile |
| java_server | `java Server.java N` | JDK 21 |
| php_server | `php -S 127.0.0.1:N -t DIR DIR/index.php` | The router argument is needed so `/hello` reaches `index.php` |
| go_server | `go run . N` | Timeout 120 s |

`Process` takes no environment, so each server takes its port from the command line (and from `PORT` as a fallback).

## Tests and the workflow

`tests/core/examples/test_example_projects.py` runs the examples that need only Python and Node. `tests/core/examples/test_toolchain_examples.py` (marker `toolchains`, off by default) runs every external-tool example twice, once through its `main.py` and once through `cornea serve --run ... --url ... --mode proxy`, and skips what is not installed. `.github/workflows/examples.yml` installs each toolchain on Windows and runs it weekly, on manual dispatch and on pull requests that touch `examples/`. It is not part of the required `ci` check.

The packaging test (`tests/core/examples/test_packaging.py`) is part of the same workflow: it builds a small app with PyInstaller and checks that the frozen program serves its page.

The .NET, Java, PHP and Go servers were written without those toolchains installed; the workflow is their only test.
