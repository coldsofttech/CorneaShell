# Flask

A Flask app mounted in the same process as Cornea.

**You need:** Flask (`uv sync --group examples`, or `pip install flask`).

## Create this kind of app

Write an ordinary Flask app. Flask speaks WSGI, so Cornea mounts it in the same process; nothing about the app changes.

```python
from flask import Flask, jsonify, request

app = Flask(__name__)


@app.get("/")
def index() -> str:
    return "<h1>Hello from Flask</h1>"


@app.get("/hello")
def hello():
    return jsonify(message=f"Hello, {request.args.get('name', 'world')}!")
```

Routes may be anywhere except under `/api` and `/health`, which Cornea answers itself. Use `url_for("static", ...)` or a `/static/...` path for your own CSS and JavaScript; the strict policy allows only files from your own address.

## Run it

### With the command line

```bash
uv run cornea open --wsgi flask_example:app --app-dir examples/flask_app --title "Flask"
```

### With the Python package

```bash
uv run python examples/flask_app/main.py
uv run python examples/flask_app/main.py --frameless
```

```python
from cornea import Shell, Window, Wsgi

Shell(Wsgi("flask_example:app", app_dir="examples/flask_app"), window=Window(title="Flask")).run()
```

The same entry point takes `--headless` (no window; it prints an address to open in a browser).

## Using Cornea features

Cornea answers under `/api` (and `/health`) on the same address as your page, so the page reaches it with plain `fetch()` calls. Add Cornea's one small script to the page your Flask route returns (the `<head>` of `PAGE` in `flask_example.py`):

```html
<script src="/api/client.js"></script>
```

It defines `window.cornea`. Dialogs and your own actions work straight away; opening files, notifications, dropped files and downloads are off until you allow them.

### Your own actions (Python only)

An action is a Python function the page can call. Register it on the shell:

```python
shell = Shell(Wsgi("flask_example:app", app_dir="examples/flask_app"))


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
uv run cornea open --wsgi flask_example:app --app-dir examples/flask_app --notifications
```

To show a toast from a Flask view, give the module a callback that `main.py` fills in once the shell exists:

```python
notify = lambda title, message: None  # flask_example.py: replaced by main.py


@app.post("/finished")
def finished():
    notify("Export finished", "3 files were saved.")
    return jsonify(ok=True)


# main.py
import flask_example

flask_example.notify = shell.show_notification
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
uv run cornea open --wsgi flask_example:app --app-dir examples/flask_app --open-files --drop-files --downloads
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
