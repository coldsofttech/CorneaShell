# Examples

Small projects, each showing one way to give Cornea a web UI. Run them from the repository root after `uv sync`. Each one is also run by the test suite (except React, which needs a build).

| Example | What it shows | Command line | Python |
| --- | --- | --- | --- |
| [static_html](static_html) | Plain HTML, CSS and JavaScript, with your own title bar in a frameless window | `uv run cornea open examples/static_html --frameless` | `uv run python examples/static_html/main.py` |
| [react_vite](react_vite) | A React project built with Vite, or run as a dev server with hot reload | `npm install && npm run build` in the folder, then `uv run cornea open examples/react_vite/dist --frameless` | `uv run python examples/react_vite/main.py` (or `--dev`) |
| [fastapi_app](fastapi_app) | A FastAPI backend with its own routes and a native action, or the whole FastAPI app served by Cornea | `uv run cornea open --asgi main:app --app-dir examples/fastapi_app` | `uv run python examples/fastapi_app/main.py` (or `--mount`) |
| [flask_app](flask_app) | A Flask app mounted in the same process | `uv run cornea open --wsgi flask_example:app --app-dir examples/flask_app` | `uv run python examples/flask_app/main.py` |
| [django_app](django_app) | A one-file Django site mounted in the same process | `uv run cornea open --asgi django_example:application --app-dir examples/django_app` | `uv run python examples/django_app/main.py` |
| [node_server](node_server) | A Node.js server that Cornea starts for you, or one you started yourself | `node examples/node_server/server.js`, then `uv run cornea open http://127.0.0.1:3000` (add `--mode proxy` for the proxy; needs `cornea-shell[proxy]`) | `uv run python examples/node_server/main.py` (or `--external`, `--mode proxy`) |

Each Python entry point opens a window. Add `--headless` to skip the window: it prints a line of JSON with an address, and you open that address in a browser. (A direct address needs a window, so the Node example needs `--mode proxy` for that.)

More examples. The last column says where each one is tested.

| Example | What it shows | Python | Tested |
| --- | --- | --- | --- |
| [vue_vite](vue_vite) | A Vue project built with Vite, built or as a dev server | `uv run python examples/vue_vite/main.py` (or `--dev`) | Test suite |
| [htmx_fastapi](htmx_fastapi) | HTMX with FastAPI templates | `uv run python examples/htmx_fastapi/main.py` | Test suite |
| [streamlit_app](streamlit_app) | A Streamlit app through the proxy, WebSocket included | `uv run python examples/streamlit_app/main.py` | Examples workflow; also the test suite when `streamlit` is installed |
| [mkdocs_site](mkdocs_site) | A MkDocs site, built or live | `uv run python examples/mkdocs_site/main.py` (or `--live`) | Examples workflow; also the test suite when `mkdocs` is installed |
| [dotnet_server](dotnet_server) | An ASP.NET Core server (needs the .NET 8 SDK) | `uv run python examples/dotnet_server/main.py` | Examples workflow only (not run on the author's machine) |
| [java_server](java_server) | A JDK `HttpServer` (needs JDK 21) | `uv run python examples/java_server/main.py` | Examples workflow only (not run on the author's machine) |
| [php_server](php_server) | PHP's built-in server (needs PHP 8) | `uv run python examples/php_server/main.py` | Examples workflow only (not run on the author's machine) |
| [go_server](go_server) | A Go `net/http` server (needs Go 1.21) | `uv run python examples/go_server/main.py` | Examples workflow only (not run on the author's machine) |

Streamlit, MkDocs and Jinja2 are in an optional group: `uv sync --group examples`. The examples workflow runs every external-tool example weekly, both through its Python script and through the `cornea` command.

## A dev server through Cornea

The React project also runs as a dev server with hot reload. Cornea can serve it from its own address (proxy mode), so the page gets the security layer, the window controls and a frameless window:

```bash
cd examples/react_vite
npm run dev                  # Vite listens on http://localhost:5173
# in another terminal, from the repository root:
uv run cornea open http://localhost:5173 --mode proxy --csp-profile dev --frameless
```

The Python way is `uv run python examples/react_vite/main.py --dev`: it starts Vite for you and stops it when the window closes.

Edit `src/App.jsx` and the window updates without reloading. `--csp-profile dev` is needed because Vite injects inline scripts and styles; it is for development only. Proxy mode needs `pip install "cornea-shell[proxy]"` (or `uv sync --extra proxy` in this repository).

## Trying one in a browser first

Add `serve` instead of `open` to see a page without a window. For example:

```bash
uv run cornea serve examples/static_html
```

It prints a line of JSON with an address. Open that address in a browser.

## Things the examples show

- **The strict security policy.** The page may load scripts and styles from its own files only. There are no inline `<script>` blocks or `style=` attributes in the bundle and app examples. The Node example is not served by Cornea, so it is not covered by that policy.
- **Same-origin calls.** The pages reach Cornea and their own backends with plain `fetch()` calls to the address they were loaded from. No CORS setup is needed.
- **What belongs to Cornea.** Under `/api` and at `/health`, Cornea answers. Your Flask or Django routes can be anywhere else.
- **A custom title bar** appears only when `GET /api/window` says the window is frameless.

## Other frameworks

Anything that builds to a folder of static files works like the React example: give Cornea the build folder. That includes Vue, Svelte, Angular, Astro, and a Next.js static export. Any other ASGI or WSGI framework (Starlette, Quart, Bottle, Pyramid) works like the FastAPI, Flask and Django examples, and any dev server you already run works like the Node example.
