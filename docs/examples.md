# Example entry points

Each folder in `examples/` has a `main.py` that builds a `Shell` in `build_shell(...)` and runs it in `main()`, and a README with the steps to create that kind of app and run it. Tests load these files and call `build_shell(headless=True)`. See [examples/README.md](../examples/README.md) for the list.

| Example | Source |
| --- | --- |
| static_html, react_vite, vue_vite | `Static(folder)`; the Vite examples can use `Process("npm run dev ...", mode="proxy")` with `DEV_CSP` |
| fastapi_app, htmx_fastapi | `Static` plus routers, or `Asgi("main:app")` |
| flask_app, django_app | `Wsgi(...)`, `Asgi(...)` |
| node_server, streamlit_app, mkdocs_site | `Process(...)` or `Url(...)`, usually in proxy mode |
| dotnet_server, java_server, php_server, go_server | `Process(command, mode="proxy")`; each takes its port from the command line |

Headless runs pass `window=None` and print `ready_line(shell)` from `on_ready`.

## Tests and the workflow

`tests/core/examples/test_example_projects.py` runs the examples that need only Python and Node. `tests/core/examples/test_toolchain_examples.py` (marker `toolchains`, off by default) runs every external-tool example twice, once through its `main.py` and once through `cornea serve --run ... --url ... --mode proxy`, and skips what is not installed. `.github/workflows/examples.yml` installs each toolchain on Windows and runs it weekly, on manual dispatch and on pull requests that touch `examples/`. It is not part of the required `ci` check.

The packaging test (`tests/core/examples/test_packaging.py`) is part of the same workflow: it builds a small app with PyInstaller and checks that the frozen program serves its page.

The .NET, Java, PHP and Go servers were written without those toolchains installed; the workflow is their only test.
