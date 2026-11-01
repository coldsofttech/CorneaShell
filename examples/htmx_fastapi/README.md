# HTMX with FastAPI

![Cornea Shell](https://img.shields.io/badge/Cornea%20Shell-0.1-0A7EA4?logo=windows&logoColor=white) ![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-ASGI-009688?logo=fastapi&logoColor=white) ![HTMX](https://img.shields.io/badge/HTMX-2-3366CC?logo=htmx&logoColor=white) ![Jinja2](https://img.shields.io/badge/Jinja2-templates-B41717?logo=jinja&logoColor=white) [![CI](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml)

FastAPI answers with small pieces of HTML (Jinja2 templates) and HTMX puts them in the page, with no JavaScript of your own.

**You need:** `uv sync --group examples` (FastAPI and Jinja2).

## Create this kind of app

1. Put HTMX in your `static/` folder. A CDN script is blocked by the strict policy, so copy `htmx.min.js` from the `htmx.org` npm package and load it with `<script src="/static/htmx.min.js">`.
2. Return HTML fragments from templates:

```python
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/greeting")
def greeting(request: Request, name: str = "world"):
    return templates.TemplateResponse(request, "greeting.html", {"name": name})
```

1. Use HTMX attributes in the page: `<button hx-get="/greeting?name=Ada" hx-target="#out">Greet</button>`.

HTMX adds an inline `<style>` by default, which the policy blocks; turn that off with `<meta name="htmx-config" content='{"includeIndicatorStyles": false}'>`. Your routes may be anywhere except under `/api` and `/health`.

## Run it

### With the command line

```bash
uv run cornea open --asgi main:app --app-dir examples/htmx_fastapi --title "HTMX"
```

### With the Python package

```bash
uv run python examples/htmx_fastapi/main.py
```

```python
from cornea import Asgi, Shell

Shell(Asgi("main:app", app_dir="examples/htmx_fastapi")).run()
```

The same entry point takes `--headless` (no window; it prints an address to open in a browser).

## Using Cornea features

Cornea answers under `/api` (and `/health`) on the same address as your page, so the page reaches it with plain `fetch()` calls. Add Cornea's one small script to `templates/index.html`, before the HTMX script:

```html
<script src="/api/client.js"></script>
```

It defines `window.cornea`. Dialogs and your own actions work straight away; opening files, notifications, dropped files and downloads are off until you allow them.

### Your own actions (Python only)

An action is a Python function the page can call. Register it on the shell:

```python
shell = Shell(Asgi("main:app", app_dir="examples/htmx_fastapi"))


@shell.action("shout")
def shout(text: str) -> str:
    return text.upper()


shell.run()
```

```javascript
const result = await cornea.call("shout", { text: "hello" });   // "HELLO"
```

The command line cannot register actions, because they are Python code. From the command line you get the built-in ones: `choose_folder`, `choose_file`, `save_file`, `open_external` and `platform_info`. Switch one off with `--disable-action NAME`.

### Notifications

Windows draws the toast. It needs the extra: `pip install "cornea-shell[notifications]"`.

```python
from cornea import Bridge

shell = Shell(..., bridge=Bridge(notifications=True))  # lets the page show one too
shell.show_notification("Export finished", "3 files were saved.", notification_id="export-1")
```

```javascript
await cornea.call("show_notification", {
  title: "Export finished",
  message: "3 files were saved.",
  notification_id: "export-1",
});
cornea.on("notification-click", (detail) => console.log(detail.id));
```

From the command line, add `--notifications` so the page may show them:

```bash
uv run cornea open --asgi main:app --app-dir examples/htmx_fastapi --notifications
```

A route can show a toast too, since it runs in the same process: have `main.py` set a module-level `notify = shell.show_notification` that your route calls.

### Files and folders

```javascript
const folder = await cornea.call("choose_folder");               // a path, or null
const files = await cornea.call("choose_file", { multiple: true, file_types: ["Images (*.png;*.jpg)"] });
const target = await cornea.call("save_file", { filename: "report.pdf" });   // nothing is written
await cornea.call("open_file", { path: target });               // needs open files on
await cornea.call("reveal", { path: target });                  // show it in Explorer
```

Dialogs are always available. Opening a file in its program (`open_file`, `reveal`), dropped files and downloads are separate switches:

```python
from cornea import Bridge, Window

shell = Shell(..., bridge=Bridge(open_files=True), window=Window(drop_files=True, downloads=True))
```

```bash
uv run cornea open --asgi main:app --app-dir examples/htmx_fastapi --open-files --drop-files --downloads
```

Dropped files arrive as an event: `cornea.on("drop", (detail) => console.log(detail.paths))`. Programs and scripts (`.exe`, `.bat`, `.lnk` and similar) are never opened.

### Telling the page, and keeping the window open

```python
shell.notify("export-done", {"rows": 3})  # the page gets a "cornea:export-done" event


@shell.close_guard
def busy() -> bool:
    return export_running  # True keeps the window open
```

```javascript
cornea.on("export-done", (detail) => console.log(detail.rows));
await cornea.closeGuard(true);   // the page can hold the window open itself, also from the CLI
```
