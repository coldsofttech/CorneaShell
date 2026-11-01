# Examples

Small projects, each showing one way to give Cornea a web UI. Every folder has its own README that explains how to create that kind of app, how to run it with the `cornea` command and with the Python package, and how to use actions, notifications and files.

Run them from the repository root after `uv sync` (`uv sync --group examples` for the ones that need Flask, Django, Streamlit, MkDocs or Jinja2).

| Example | What it shows |
| --- | --- |
| [static_html](static_html) | Plain HTML, CSS and JavaScript, with its own title bar |
| [react_vite](react_vite) | React with Vite, built or as a dev server |
| [vue_vite](vue_vite) | Vue with Vite, built or as a dev server |
| [fastapi_app](fastapi_app) | A FastAPI backend with routes and a native action |
| [flask_app](flask_app) | A Flask app in the same process |
| [django_app](django_app) | A one-file Django site in the same process |
| [htmx_fastapi](htmx_fastapi) | HTMX with FastAPI templates |
| [streamlit_app](streamlit_app) | Streamlit through the proxy, WebSocket included |
| [mkdocs_site](mkdocs_site) | A MkDocs site, built or live |
| [node_server](node_server) | A Node.js server Cornea starts, or one you started |
| [dotnet_server](dotnet_server) | ASP.NET Core (.NET 8 SDK) |
| [java_server](java_server) | A JDK `HttpServer` (JDK 21) |
| [php_server](php_server) | PHP's built-in server (PHP 8) |
| [go_server](go_server) | A Go `net/http` server (Go 1.21) |

Every `main.py` opens a window. Add `--headless` to skip it: the script prints a line of JSON with an address to open in a browser. To try any folder in a browser first, use `uv run cornea serve <folder>`.

Anything that builds to a folder of static files (Svelte, Angular, Astro, a Next.js static export) works like the React example. Any other ASGI or WSGI framework works like FastAPI, Flask or Django, and any dev server you already run works like the Node example.
