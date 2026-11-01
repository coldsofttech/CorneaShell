# MkDocs

A small MkDocs site shown in a window, like an offline help viewer.

**You need:** MkDocs (`uv sync --group examples`).

## Create this kind of app

```bash
pip install mkdocs
mkdocs new my-docs
cd my-docs
mkdocs build          # writes site/: plain static files
```

`mkdocs.yml` names the pages (`nav`) and the output folder (`site_dir: site`). Cornea shows the built `site/` folder as it is, or runs `mkdocs serve` for live reloading.

In the built site the default theme has a few inline scripts and loads code highlighting from a CDN. The strict policy blocks them, so highlighting and search do not work there; reading and navigation do.

## Run it

### With the command line

```bash
uv run mkdocs build -f examples/mkdocs_site/mkdocs.yml
uv run cornea open examples/mkdocs_site/site

# live: mkdocs serve through the proxy (needs the proxy extra)
uv run cornea open --url http://127.0.0.1:8000 --run "uv run mkdocs serve -a 127.0.0.1:8000" \
  --run-cwd examples/mkdocs_site --mode proxy --csp-profile dev
```

### With the Python package

```bash
uv run python examples/mkdocs_site/main.py          # builds, then shows the site
uv run python examples/mkdocs_site/main.py --live   # mkdocs serve, reloads on edits
```

```python
from cornea import Shell, Static

Shell(Static("examples/mkdocs_site/site")).run()
```

The same entry point takes `--headless` (no window; it prints an address to open in a browser).

## Using Cornea features

Cornea answers under `/api` (and `/health`) on the same address as your page, so the page reaches it with plain `fetch()` calls. Add Cornea's one small script to every page, through a theme override (`theme.custom_dir` in `mkdocs.yml`, then a `<script>` tag in `overrides/main.html`):

```html
<script src="/api/client.js"></script>
```

It defines `window.cornea`. Dialogs and your own actions work straight away; opening files, notifications, dropped files and downloads are off until you allow them.

### Your own actions (Python only)

An action is a Python function the page can call. Register it on the shell:

```python
shell = Shell(Static("examples/mkdocs_site/site"))


@shell.action("shout")
def shout(text: str) -> str:
    return text.upper()


shell.run()
```

```javascript
const result = await cornea.call("shout", { text: "hello" });   // "HELLO"
```

The command line cannot register actions, because they are Python code. From the command line you get the built-in ones: `choose_folder`, `choose_file`, `save_file`, `open_external` and `platform_info`. Switch one off with `--disable-action NAME`. A help viewer rarely needs them; `open_external` (open a link in the system browser) is the one most docs sites want.

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
uv run cornea open examples/mkdocs_site/site --notifications
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
uv run cornea open examples/mkdocs_site/site --open-files --drop-files --downloads
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

`--live` uses the development security policy, because MkDocs reloads the page over a WebSocket and injects inline scripts.
