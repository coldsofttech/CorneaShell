# Node.js

![Cornea Shell](https://img.shields.io/badge/Cornea%20Shell-0.1-0A7EA4?logo=windows&logoColor=white) ![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white) ![Node.js](https://img.shields.io/badge/Node.js-20%2B-5FA04E?logo=nodedotjs&logoColor=white) [![Examples workflow](https://github.com/coldsofttech/CorneaShell/actions/workflows/examples.yml/badge.svg)](https://github.com/coldsofttech/CorneaShell/actions/workflows/examples.yml)

A Node.js server that Cornea starts for you, or one you started yourself.

**You need:** Node.js. No packages.

## Create this kind of app

Any server that listens on a port works. This one uses only Node's own `http` module, and takes the port from its first argument (or `PORT`) so Cornea can choose it:

```javascript
const http = require("node:http");
const port = Number(process.argv[2] ?? process.env.PORT ?? 3000);

http.createServer((request, response) => {
  response.setHeader("Content-Type", "text/html; charset=utf-8");
  response.end("<h1>Hello from Node</h1>");
}).listen(port, "127.0.0.1");
```

Listen on `127.0.0.1`, not on all addresses.

## Run it

### With the command line

```bash
# a server you started yourself
node examples/node_server/server.js
uv run cornea open http://127.0.0.1:3000                       # direct: a plain window
uv run cornea open http://127.0.0.1:3000 --mode proxy          # through Cornea (needs the proxy extra)

# Cornea starts it
uv run cornea open --url http://127.0.0.1:3000 --run "node server.js 3000" --run-cwd examples/node_server --mode proxy
```

### With the Python package

```bash
uv run python examples/node_server/main.py                    # Cornea starts server.js
uv run python examples/node_server/main.py --external         # use the one you started
uv run python examples/node_server/main.py --mode proxy --frameless
```

```python
from cornea import Process, Shell, Url

Shell(
    Process(
        ("node", "server.js", "3000"),
        url="http://127.0.0.1:3000",
        cwd="examples/node_server",
        mode="proxy",
    )
).run()
Shell(Url("http://127.0.0.1:3000", mode="proxy")).run()  # a server you started
```

A direct address needs a window, so `--headless` needs `--mode proxy`.

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
shell = Shell(
    Process(
        ("node", "server.js", "3000"),
        url="http://127.0.0.1:3000",
        cwd="examples/node_server",
        mode="proxy",
    )
)


@shell.action("shout")
def shout(text: str) -> str:
    return text.upper()


shell.run()
```

```javascript
const result = await cornea.call("shout", { text: "hello" });   // "HELLO"
```

The command line cannot register actions, because they are Python code. From the command line you get the built-in ones: `choose_folder`, `choose_file`, `save_file`, `open_external` and `platform_info`. Switch one off with `--disable-action NAME`. Your server is Node, so the Python script that starts the shell is where actions, `show_notification` and `notify` live.

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
uv run cornea open --url http://127.0.0.1:3000 --run "node server.js 3000" --mode proxy --notifications
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
uv run cornea open --url http://127.0.0.1:3000 --run "node server.js 3000" --mode proxy --open-files --drop-files --downloads
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

These features need `--mode proxy`. In direct mode the page is not served by Cornea; `--js-api` can give it the window controls and native actions, but every page the window loads then gets those powers, so use it only for pages you trust.
