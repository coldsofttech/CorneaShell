# Streamlit

A small Streamlit app shown in a window. Streamlit talks over a WebSocket, so this also shows that the proxy forwards WebSockets.

**You need:** Streamlit (`uv sync --group examples`) and `pip install "cornea-shell[proxy]"`.

## Create this kind of app

```python
# app.py
import streamlit as st

st.title("Hello from Streamlit")
name = st.text_input("Your name", "Ada")
if st.button("Greet"):
    st.success(f"Hello, {name}!")
```

Cornea does not host Streamlit. It starts `streamlit run` as a command and shows its address through the proxy, so the command must say which port to use: `--server.port N --server.headless true`. Streamlit's page uses inline scripts and styles, so it needs the development security policy (`--csp-profile dev`): fine for a tool, not for something you ship.

## Run it

### With the command line

```bash
uv run cornea open --url http://127.0.0.1:8501 \
  --run "uv run streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false" \
  --run-cwd examples/streamlit_app --mode proxy --csp-profile dev
```

### With the Python package

```bash
uv run python examples/streamlit_app/main.py
```

```python
from cornea import DEV_CSP, Process, Security, Shell

source = Process(
    (
        "python",
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.headless",
        "true",
        "--server.port",
        "8501",
    ),
    url="http://127.0.0.1:8501",
    cwd="examples/streamlit_app",
    mode="proxy",
)
Shell(source, security=Security(csp=DEV_CSP)).run()
```

The same entry point takes `--headless` (no window; it prints an address to open in a browser).

## Using Cornea features

Cornea answers under `/api` (and `/health`) on the same address as your page, so the page reaches it with plain `fetch()` calls. Add Cornea's one small script to an HTML component you embed with `st.components.v1.html`:

```html
<script src="/api/client.js"></script>
```

It defines `window.cornea`. Dialogs and your own actions work straight away; opening files, notifications, dropped files and downloads are off until you allow them.

### Your own actions (Python only)

An action is a Python function the page can call. Register it on the shell:

```python
shell = Shell(source, security=Security(csp=DEV_CSP))


@shell.action("shout")
def shout(text: str) -> str:
    return text.upper()


shell.run()
```

```javascript
const result = await cornea.call("shout", { text: "hello" });   // "HELLO"
```

The command line cannot register actions, because they are Python code. From the command line you get the built-in ones: `choose_folder`, `choose_file`, `save_file`, `open_external` and `platform_info`. Switch one off with `--disable-action NAME`. Streamlit pages are built from Python widgets, so the most useful form here is to call `shell.show_notification(...)` or `shell.notify(...)` from the Python process that holds the shell, for example from a thread that watches a job.

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
uv run cornea open --url http://127.0.0.1:8501 --run "..." --mode proxy --csp-profile dev --notifications
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
uv run cornea open --url http://127.0.0.1:8501 --run "..." --mode proxy --csp-profile dev --open-files --drop-files --downloads
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

Streamlit renders your widgets itself, so there is rarely a place for `cornea.call`. The Python-side calls (`shell.show_notification`, `shell.notify`) are the natural fit; the page-side snippets apply if you embed your own HTML.
