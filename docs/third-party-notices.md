# Third-party notices

Cornea Shell is released under the [MIT license](../LICENSE). This page lists the packages it depends on at runtime and the licenses they use. Development tools (test runners, linters, build tools) are not shipped and are not listed.

Every runtime dependency uses a permissive license, or the file-level MPL-2.0 for `certifi`. None uses GPL, LGPL or AGPL, so all of them can be used alongside the MIT license.

## Direct dependencies

These install with `pip install cornea-shell`.

| Package      | License      | Used for                                             |
| ------------ | ------------ | ---------------------------------------------------- |
| `fastapi`    | MIT          | the local server and your own routes                 |
| `pywebview`  | BSD-3-Clause | the native window (Windows only)                     |
| `rich`       | MIT          | the tables and messages the `cornea` command prints  |
| `typer`      | MIT          | the `cornea` command                                 |
| `uvicorn`    | BSD-3-Clause | serving the app                                      |

## Optional extras

These install only when you ask for them.

| Extra           | Package                                 | License      | Used for                                  |
| --------------- | --------------------------------------- | ------------ | ----------------------------------------- |
| `wsgi`          | `a2wsgi`                                | Apache-2.0   | mounting Flask and other WSGI apps        |
| `proxy`         | `httpx`                                 | BSD-3-Clause | showing another server's pages            |
| `proxy`         | `websockets`                            | BSD-3-Clause | forwarding WebSockets through the proxy   |
| `notifications` | `winrt-runtime` and five `winrt-windows-*` packages | MIT | Windows notifications (Windows only) |

## All runtime dependencies, by license

This counts the direct dependencies, the optional extras and everything they depend on: 39 packages in all, on Windows.

| License       | Packages |
| ------------- | -------- |
| MIT           | 22       |
| BSD-3-Clause  | 10       |
| Apache-2.0    | 2        |
| BSD-2-Clause  | 1        |
| ISC           | 1        |
| MIT-0         | 1        |
| MPL-2.0       | 1        |
| PSF-2.0       | 1        |

## Notes

- **Windows-only packages.** `pywebview` brings `pythonnet`, `clr-loader`, `cffi`, `pycparser`, `bottle` and `proxy_tools` (MIT, BSD-3-Clause, MIT-0 and similar). They are installed on Windows only, which is the only platform Cornea Shell supports.
- **MPL-2.0.** `certifi` (the CA certificate bundle, reached through `httpx` with the `proxy` extra) is MPL-2.0, a file-level license. It is installed as an ordinary dependency and is not copied or changed here.
- **Vendored file.** The HTMX example ships `htmx.min.js` (HTMX 2.0.11 from the `htmx.org` package, Zero-Clause BSD) in `examples/htmx_fastapi/static`. The example is not part of the installed package.
- **Examples.** The example projects pull in their own packages (React, Vue, Vite, Flask, Django, Streamlit, MkDocs and the Go, Java, PHP and .NET tooling). They are not dependencies of Cornea Shell and are not installed with it.

## Keeping this up to date

The lists above come from the locked dependencies (`uv export --no-default-groups --all-extras --no-emit-project`) and the license each installed package declares. Update this page when a runtime dependency is added, removed or upgraded to a new major version.
