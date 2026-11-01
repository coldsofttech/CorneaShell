# Vue + Vite

A Vue project built with Vite, with its own title bar when the window is frameless. It has the same shape as the React example.

**You need:** Node.js 20 or newer.

## Create this kind of app

```bash
npm create vue@latest vue_vite      # or: npm create vite@latest vue_vite -- --template vue
cd vue_vite
npm install
npm run build
```

Cornea serves `dist/` as it is. To reach Cornea from a component, add `<script src="/api/client.js"></script>` to `index.html` and use `window.cornea` (this example keeps its own few calls in `src/cornea.js`).

## Run it

### With the command line

```bash
cd examples/vue_vite && npm install && npm run build && cd ../..
uv run cornea open examples/vue_vite/dist --frameless

cd examples/vue_vite && npm run dev          # dev server, in another terminal
uv run cornea open http://127.0.0.1:5173 --mode proxy --csp-profile dev --frameless
```

### With the Python package

```bash
uv run python examples/vue_vite/main.py
uv run python examples/vue_vite/main.py --dev     # Vite with hot reload
```

```python
from cornea import Shell, Static, Window

Shell(Static("examples/vue_vite/dist"), window=Window(title="Vue + Vite", frameless=True)).run()
```

The same entry point takes `--headless` (no window; it prints an address to open in a browser).

## Using Cornea features

Cornea answers under `/api` (and `/health`) on the same address as your page, so the page reaches it with plain `fetch()` calls. Add Cornea's one small script to `index.html`:

```html
<script src="/api/client.js"></script>
```

It defines `window.cornea`. Dialogs and your own actions work straight away; opening files, notifications, dropped files and downloads are off until you allow them.

### Your own actions (Python only)

An action is a Python function the page can call. Register it on the shell:

```python
shell = Shell(Static("examples/vue_vite/dist"))


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
uv run cornea open examples/vue_vite/dist --notifications
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
uv run cornea open examples/vue_vite/dist --open-files --drop-files --downloads
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

`--dev` uses the development security policy, because Vite injects inline scripts. The built version uses the strict one.
