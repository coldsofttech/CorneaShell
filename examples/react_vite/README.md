# React + Vite

![Cornea Shell](https://img.shields.io/badge/Cornea%20Shell-0.1-0A7EA4?logo=windows&logoColor=white) ![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white) ![React](https://img.shields.io/badge/React-19-20232A?logo=react&logoColor=white) ![Vite](https://img.shields.io/badge/Vite-dev%20server-646CFF?logo=vite&logoColor=white) ![Node.js](https://img.shields.io/badge/Node.js-20%2B-5FA04E?logo=nodedotjs&logoColor=white) [![CI](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml)

A React project built with Vite. Cornea shows the build folder, or runs the Vite dev server with hot reload.

**You need:** Node.js 20 or newer.

## Create this kind of app

```bash
npm create vite@latest react_vite -- --template react
cd react_vite
npm install
npm run build          # writes dist/: static files, fingerprinted under assets/
```

Cornea needs nothing from your React code. It serves `dist/` and falls back to `index.html` for page routes, so a client-side router works. To reach Cornea from a component, add `<script src="/api/client.js"></script>` to `index.html` and use `window.cornea` (this example keeps its own few calls in `src/cornea.js`).

## Run it

### With the command line

```bash
cd examples/react_vite && npm install && npm run build && cd ../..
uv run cornea open examples/react_vite/dist --frameless

# dev server with hot reload (needs: pip install "cornea-shell[proxy]")
cd examples/react_vite && npm run dev          # in another terminal
uv run cornea open http://127.0.0.1:5173 --mode proxy --csp-profile dev --frameless
```

`--csp-profile dev` is only for the dev server, because Vite injects inline scripts.

### With the Python package

```bash
uv run python examples/react_vite/main.py          # built files
uv run python examples/react_vite/main.py --dev     # starts Vite for you, stops it with the window
```

```python
from cornea import DEV_CSP, Process, Security, Shell, Static

Shell(Static("examples/react_vite/dist"))  # built
Shell(
    Process(
        "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
        url="http://127.0.0.1:5173",
        cwd="examples/react_vite",
        mode="proxy",
    ),
    security=Security(csp=DEV_CSP),  # dev only
)
```

The same entry point takes `--headless` (no window; it prints an address to open in a browser).

## Using Cornea features

Cornea answers under `/api` (and `/health`) on the same address as your page, so the page reaches it with plain `fetch()` calls. Add Cornea's one small script to `index.html` (Vite leaves it alone):

```html
<script src="/api/client.js"></script>
```

It defines `window.cornea`. Dialogs and your own actions work straight away; opening files, notifications, dropped files and downloads are off until you allow them.

### Your own actions (Python only)

An action is a Python function the page can call. Register it on the shell:

```python
shell = Shell(Static("examples/react_vite/dist"))


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
uv run cornea open examples/react_vite/dist --notifications
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
uv run cornea open examples/react_vite/dist --open-files --drop-files --downloads
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
