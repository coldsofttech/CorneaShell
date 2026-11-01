# FastAPI

A FastAPI backend with its own routes and a native action. Cornea can serve a folder plus your routers, or the whole FastAPI app.

**You need:** Cornea (FastAPI is already one of its dependencies).

## Create this kind of app

Write your routes on an `APIRouter`. Cornea mounts them under `/api`, behind the session cookie, so they are not reachable from other programs on the machine.

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/greeting")
def greeting(name: str = "world") -> dict[str, str]:
    return {"message": f"Hello, {name}!"}
```

The page calls `fetch("/api/greeting?name=Ada")`. Static files (`web/`) are given to Cornea as a folder.

If you would rather hand over a whole `FastAPI()` app, Cornea mounts it at the root. `/api` and `/health` still belong to Cornea, so your routes live elsewhere (here `/greeting`, and the page reads that URL from a `<meta>` tag).

## Run it

### With the command line

```bash
# the whole FastAPI app, imported as module:attribute
uv run cornea open --asgi main:app --app-dir examples/fastapi_app
```

A router plus a folder is the Python form below; the command line serves either a folder (`cornea open DIR`) or an app (`--asgi`).

### With the Python package

```bash
uv run python examples/fastapi_app/main.py            # folder + routers
uv run python examples/fastapi_app/main.py --mount     # the whole FastAPI app
```

```python
from cornea import Asgi, Shell, Static

Shell(Static("examples/fastapi_app/web"), routers=[router]).run()
Shell(Asgi("main:app", app_dir="examples/fastapi_app")).run()
```

The same entry point takes `--headless` (no window; it prints an address to open in a browser).

## Using Cornea features

Cornea answers under `/api` (and `/health`) on the same address as your page, so the page reaches it with plain `fetch()` calls. Add Cornea's one small script to `web/index.html`:

```html
<script src="/api/client.js"></script>
```

It defines `window.cornea`. Dialogs and your own actions work straight away; opening files, notifications, dropped files and downloads are off until you allow them.

### Your own actions (Python only)

An action is a Python function the page can call. Register it on the shell:

```python
shell = Shell(Static("examples/fastapi_app/web"), routers=[router])


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
uv run cornea open --asgi main:app --app-dir examples/fastapi_app --notifications
```

A route can show one too, since it runs in the same process as the shell:

```python
@router.post("/finished")
def finished() -> dict[str, bool]:
    shell.show_notification("Export finished", "3 files were saved.")
    return {"ok": True}
```

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
uv run cornea open --asgi main:app --app-dir examples/fastapi_app --open-files --drop-files --downloads
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
