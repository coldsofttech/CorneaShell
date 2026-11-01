# Static HTML

Plain HTML, CSS and JavaScript in a frameless window, with the page's own title bar.

**You need:** nothing beyond Cornea. No build step.

## Create this kind of app

Make a folder with an `index.html`, a stylesheet and a script. Because Cornea's default security policy only allows scripts and styles from your own files, keep them in separate files: no inline `<script>` blocks and no `style=` attributes.

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Plain HTML</title>
    <link rel="stylesheet" href="style.css" />
    <script type="module" src="app.js"></script>
  </head>
  <body>
    <h1>Hello</h1>
  </body>
</html>
```

That folder is the whole app. Cornea serves it as it is.

## Run it

### With the command line

```bash
uv run cornea open examples/static_html --frameless
uv run cornea open examples/static_html --frameless --icon examples/static_html/icon.png
uv run cornea serve examples/static_html          # no window: open the printed address in a browser
```

### With the Python package

```bash
uv run python examples/static_html/main.py
uv run python examples/static_html/main.py --remember     # reopen where it was
```

```python
from cornea import Shell, Static, Window

Shell(Static("examples/static_html"), window=Window(title="Plain HTML", frameless=True)).run()
```

The same entry point takes `--headless` (no window; it prints an address to open in a browser).

## Using Cornea features

Cornea answers under `/api` (and `/health`) on the same address as your page, so the page reaches it with plain `fetch()` calls. Add Cornea's one small script to `index.html`, before your own script:

```html
<script src="/api/client.js"></script>
```

It defines `window.cornea`. Dialogs and your own actions work straight away; opening files, notifications, dropped files and downloads are off until you allow them.

### Your own actions (Python only)

An action is a Python function the page can call. Register it on the shell:

```python
shell = Shell(Static("examples/static_html"), window=Window(title="Plain HTML"))


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
uv run cornea open examples/static_html --notifications
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
uv run cornea open examples/static_html --open-files --drop-files --downloads
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

A frameless window has no native title bar. The page asks `GET /api/window` whether it is frameless and draws its own bar with `cornea.window.minimize()`, `maximize()` and `close()`; give the empty part of the bar the class `pywebview-drag-region`.
