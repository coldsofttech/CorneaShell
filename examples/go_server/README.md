# Go

![Cornea Shell](https://img.shields.io/badge/Cornea%20Shell-0.1-0A7EA4?logo=windows&logoColor=white) ![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white) ![Go](https://img.shields.io/badge/Go-1.21%2B-00ADD8?logo=go&logoColor=white) [![Examples workflow](https://github.com/coldsofttech/CorneaShell/actions/workflows/examples.yml/badge.svg)](https://github.com/coldsofttech/CorneaShell/actions/workflows/examples.yml)

A Go `net/http` server that Cornea starts and shows. *Not run on the author's machine; tested by the examples workflow.*

**You need:** Go 1.21. The first start compiles, so it takes a while.

## Create this kind of app

```bash
mkdir go_server && cd go_server
go mod init example.com/server
```

```go
package main

import (
	"fmt"
	"net/http"
	"os"
)

func main() {
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "<h1>Hello from Go</h1>")
	})
	http.ListenAndServe("127.0.0.1:"+os.Args[1], nil) // the port comes from Cornea
}
```

Run it with `go run . 5104`.

## Run it

### With the command line

```bash
uv run cornea open --url http://127.0.0.1:5104 \
  --run "go run . 5104" --run-cwd examples/go_server --run-timeout 120 --mode proxy
```

Cornea starts the server, waits for the address to answer, shows it and stops the server with the window. `--mode proxy` serves the page from Cornea's own address, which is what gives it the security layer and the native features below (it needs `pip install "cornea-shell[proxy]"`). `--mode direct` just opens the address in a window; the page is then not served by Cornea and cannot use any of it.

### With the Python package

```bash
uv run python examples/go_server/main.py                  # through the proxy
uv run python examples/go_server/main.py --mode direct    # a plain window, no proxy
```

```python
from cornea import Process, Shell

source = Process(
    ("go", "run", ".", "5104"),
    url="http://127.0.0.1:5104",
    cwd="examples/go_server",
    mode="proxy",
    timeout=120,
)
Shell(source).run()
```

`Process` takes no environment, so the port is part of the command.

The same entry point takes `--headless` (no window; it prints an address to open in a browser).

## Using Cornea features

Cornea answers under `/api` (and `/health`) on the same address as your page, so the page reaches it with plain `fetch()` calls. Add Cornea's one small script to the HTML your handler writes:

```html
<script src="/api/client.js"></script>
```

It defines `window.cornea`. Dialogs and your own actions work straight away; opening files, notifications, dropped files and downloads are off until you allow them.

### Your own actions (Python only)

An action is a Python function the page can call. Register it on the shell:

```python
shell = Shell(source)


@shell.action("shout")
def shout(text: str) -> str:
    return text.upper()


shell.run()
```

```javascript
const result = await cornea.call("shout", { text: "hello" });   // "HELLO"
```

The command line cannot register actions, because they are Python code. From the command line you get the built-in ones: `choose_folder`, `choose_file`, `save_file`, `open_external` and `platform_info`. Switch one off with `--disable-action NAME`. Your server is not Python, so it cannot call `shell` directly: the Python script that starts the shell is where actions, `show_notification` and `notify` live, and the page calls them over `/api`.

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
uv run cornea open --url http://127.0.0.1:5104 --run "..." --mode proxy --notifications
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
uv run cornea open --url http://127.0.0.1:5104 --run "..." --mode proxy --open-files --drop-files --downloads
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
