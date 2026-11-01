# Cornea Shell

[![CI](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/coldsofttech/CorneaShell?logo=github)](https://github.com/coldsofttech/CorneaShell/releases)
[![PyPI](https://img.shields.io/pypi/v/cornea-shell)](https://pypi.org/project/cornea-shell/)
[![Python versions](https://img.shields.io/pypi/pyversions/cornea-shell)](https://pypi.org/project/cornea-shell/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![License](https://img.shields.io/github/license/coldsofttech/CorneaShell)](https://github.com/coldsofttech/CorneaShell/blob/main/LICENSE)

Show a web UI in a native Windows window, backed by a secured local server. You bring the UI, whether it is plain HTML, a React build, a Flask or Django site, or a page from a Node server. Cornea handles the window, the local security and the bridge to native features.

## Why Cornea Shell?

Putting a web UI on the desktop usually means bundling a whole browser, or opening a local server that every program and web page on the machine can talk to. Cornea Shell takes a smaller path: your page runs in the Windows WebView2 window that is already installed, and it is served by a local server that only that window can use.

You keep the UI you already have, and Cornea Shell adds the parts around it: the window, the security and a short, switched-off-by-default list of native features.

## What you get

- **A native window** on the Microsoft Edge WebView2 engine, with an optional frameless mode so your page draws its own title bar.
- **A secured local server.** Only your window can use it: other programs and web pages on the same machine are kept out.
- **Any web UI.** A folder of built files, a Python web app, or an address you already run.
- **Your own Python routes** next to the UI, called with ordinary `fetch()`.
- **Your dev server, started for you.** Cornea runs `npm run dev` (or any command), shows it, and stops it when the window closes.
- **Native actions your page can call:** choose a folder or file, choose where to save, open a link in the browser, read platform info, and your own.
- **Opt-in native features:** Windows notifications, opening files, dropped files and downloads. Each one stays off until you allow it.
- **A command line and a Python API** that do the same things.

## Requirements

- Windows 10 or 11 with the [Microsoft Edge WebView2 runtime](https://developer.microsoft.com/microsoft-edge/webview2/) (most up-to-date Windows installs already have it)
- Python 3.11 or newer

Other platforms are not supported yet.

## Installation

```bash
pip install cornea-shell
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add cornea-shell
```

Two optional extras: `pip install "cornea-shell[wsgi]"` to run Flask or Django apps (WSGI), and `pip install "cornea-shell[proxy]"` to serve a page from another server through Cornea (see below).

## Quick start

Show a folder of web files in a window:

```bash
cornea open path/to/your/web/folder
```

The folder needs an `index.html`. For a React, Vue, Svelte or similar project, give Cornea the folder your build produces (often `dist`).

From Python, with your own routes and a native action:

```python
from fastapi import APIRouter
from cornea import Shell, Static, Window

router = APIRouter()


@router.get("/greeting")
def greeting(name: str = "world") -> dict[str, str]:
    return {"message": f"Hello, {name}!"}


shell = Shell(Static("web/dist"), routers=[router], window=Window(title="My App"))


@shell.action("shout")
def shout(text: str) -> str:
    return text.upper()


shell.run()  # opens the window and returns when it is closed
```

Your page reaches the route at `/api/greeting` and the action with `POST /api/bridge/shout`. Both are plain `fetch()` calls to the same address the page came from.

## Choosing what to show

| You have | Give Cornea |
| --- | --- |
| Plain HTML, CSS and JavaScript | the folder: `cornea open web` |
| A React, Vue, Svelte, Angular or similar project | the build folder: `cornea open dist` |
| A dev server that is already running (Vite, Next.js, Node) | the address: `cornea open http://localhost:5173 --mode proxy --csp-profile dev` |
| A dev server you want Cornea to start | the command and its address: `cornea open --run "npm run dev" --url http://localhost:5173 --mode proxy --csp-profile dev --frameless` |
| A FastAPI or Django (ASGI) app | `cornea open --asgi myproject.asgi:application --app-dir .` |
| A Flask or Django (WSGI) app | `cornea open --wsgi myapp:app --app-dir .` |

Each of these is a small, runnable project in [examples](https://github.com/coldsofttech/CorneaShell/tree/main/examples).

### A page from a server you already run

There are two ways to show an address such as a Vite dev server:

- **Direct** (the default): the window opens the address as it is. Cornea does not serve it, so it is not behind Cornea's security, it needs the normal window frame, and the page cannot use the window controls.
- **Proxy** (`--mode proxy`, needs the `proxy` extra): Cornea fetches the pages and serves them from its own address. The page gets Cornea's security, the window controls and the frameless window, and hot reload keeps working.

Dev servers inject inline scripts and styles, which Cornea's strict content security policy blocks. For development, add `--csp-profile dev`, which allows exactly that and nothing else. Never use it for something you ship.

```bash
npm run dev   # in your project; Vite listens on http://localhost:5173
cornea open http://localhost:5173 --mode proxy --csp-profile dev --frameless
```

### A dev server that Cornea starts

Instead of starting the dev server in another terminal, let Cornea do it. Give it the command with `--run` and the address the server listens on with `--url`:

```bash
cornea open --run "npm run dev" --url http://localhost:5173 --mode proxy --csp-profile dev --frameless
```

Cornea waits until the address answers, then shows it. When the window closes, Cornea stops the command and everything it started, and it does the same if Cornea itself crashes. If the command stops early, never answers (30 seconds by default, change it with `--run-timeout`), or the address is already in use, Cornea tells you in one short message. Use `--run-cwd` to run the command in another folder.

## A frameless window with your own title bar

Run with `--frameless` and draw the title bar in your page. The buttons call Cornea:

```javascript
await fetch("/api/window/minimize", { method: "POST" });
await fetch("/api/window/maximize", { method: "POST" });
await fetch("/api/window/close", { method: "POST" });
```

Give the empty part of your bar the class `pywebview-drag-region` so it drags the window. `GET /api/window` tells your page whether the window is frameless, so it can draw the bar only when needed.

If a page comes straight from an address (the direct way) and you still want a frameless window, add `--js-api`. Cornea then gives the page the window controls and the native actions itself. Every page the window loads gets those powers, so use `--js-api` only for pages you trust. The proxy way needs no `--js-api`.

## Talking to your page, and keeping the window open

Your Python code can tell the page that something happened. The page hears it as an ordinary event on `window`, named with the prefix `cornea:`:

```python
shell.notify("export-done", {"rows": 3})  # the page gets a "cornea:export-done" event
```

```javascript
window.addEventListener("cornea:export-done", (event) => console.log(event.detail.rows));
```

**Don't lose unsaved work.** Mark the window as busy and closing it is held back, whether the person uses the close button, Alt+F4 or the taskbar. The page then gets a `cornea:close-blocked` event so it can ask:

```python
@shell.close_guard
def has_unsaved_work() -> bool:
    return editor.dirty
```

```javascript
window.addEventListener("cornea:close-blocked", () => {
  if (confirm("Close without saving?")) {
    fetch("/api/window/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: true }),
    });
  }
});
```

A page can also switch the hold on and off itself, which works from the command line too: `POST /api/window/close-guard` with `{"enabled": true}`.

**Dropped files** are off by default, because a full path says where a person keeps things. Turn them on with `--drop-files` (or `Window(drop_files=True)`) and the page gets a `cornea:drop` event whose `detail.paths` lists the full paths.

**Opening files** is off by default too. With `--open-files` (or `Bridge(open_files=True)`) the page can call the `open_file` action, which opens a document in the program Windows has for it, and `reveal`, which shows a file or folder in Explorer. Programs, scripts and shortcuts (`.exe`, `.bat`, `.ps1`, `.lnk` and similar), network paths and missing files are refused.

## Windows notifications

Windows can show a notification (a toast) with a title and a message, even while your window is minimized. Windows draws and places it, so its look is Windows' own. It needs the optional extra:

```bash
pip install "cornea-shell[notifications]"
```

Your Python code can always show one:

```python
shell.show_notification("Export finished", "3 files were saved.", notification_id="export-1")
```

A page can show one only if you allow it with `--notifications` (or `Bridge(notifications=True)`), so a page cannot raise alerts on its own:

```javascript
await fetch("/api/bridge/show_notification", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ title: "Export finished", message: "3 files were saved.", notification_id: "export-1" }),
});
```

The title (up to 64 characters) and message (up to 256) are plain text. Clicking the notification brings the window to the front and sends the page a `cornea:notification-click` event whose `detail.id` is the `notification_id`. The notification appears under your app's name and icon: Cornea registers the app id (or `Cornea.Shell`), the window title and the window icon for the current user. For a toast drawn by your own page instead, use `shell.notify()` and draw it in HTML.

## One small script for your page

Every page that talks to its window makes the same `fetch()` calls. Cornea serves them as one script, so you do not write them yourself:

```html
<script src="/api/client.js"></script>
<script type="module" src="app.js"></script>
```

```javascript
await cornea.window.minimize();                       // also maximize, restore, close, setTitle
const folder = await cornea.call("choose_folder");    // any built-in or your own action
await cornea.closeGuard(true);                        // hold the window open while busy
const stop = cornea.on("drop", (detail) => console.log(detail.paths));   // a cornea:drop event
```

`cornea.call` resolves with the action's result and rejects with a `CorneaError` (`error.unavailable` is true when the action is not available, for example a dialog with no window). The script comes from Cornea's own address, so it works under the strict security policy.

## Downloads

A page cannot save files to disk unless you allow it. With `--downloads` (or `Window(downloads=True)`) a download starts a save dialog, and the person chooses where it goes each time.

## Checking your machine

`cornea doctor` checks that Python, the WebView2 runtime and pywebview are there, that a loopback port can be opened, that your `cornea.toml` is valid, and that the log folder can be written. It exits with code 1 if something is wrong, and `--json` prints the result for other programs.

## A window icon

`--icon path/to/icon.ico` shows an icon on the window and its taskbar button. `.ico`, `.png`, `.bmp`, `.gif` and `.jpg` files work. A missing file is reported before anything starts.

## Keeping your app's state

Give the app a name and it can behave like an installed program:

```bash
cornea open web/dist --app-id com.example.notes --single-instance --remember-window
```

- **One copy at a time** (`--single-instance`): starting it again brings the first window to the front and the second start ends quietly.
- **Reopen where it was** (`--remember-window`): the window comes back at the size and place you left it. If that place is no longer on a screen, for example an unplugged monitor, Windows places it instead.
- **Its own taskbar identity:** the name also keeps the icon from being grouped under `python.exe`.

The name uses letters, digits, dots, dashes and underscores. In Python these are the `App` options. Remembered details are kept in `%LOCALAPPDATA%\Cornea\<name>`.

## Keeping your settings in a file

Put the flags you always use in a `cornea.toml` next to your project, and `cornea open` needs nothing else:

```toml
[source]
web-dist = "web/dist"

[window]
title = "My App"
frameless = true
```

Cornea also reads a `[tool.cornea]` table in `pyproject.toml`. Flags on the command line win over the file, and `--no-config` ignores it. See the [command line reference](https://github.com/coldsofttech/CorneaShell/blob/main/docs/cli-reference.md#the-settings-file) for every setting.

## When something goes wrong

Cornea is quiet by default. To see what it is doing, turn on logging:

```bash
cornea open web/dist --log-level debug --log-file cornea.log
```

`--log-level` (`debug`, `info`, `warning` or `error`) controls what appears on screen, and `--log-file` also writes everything to a file you can attach to a bug report. Debug mode (`--debug`, or `Window(debug=True)` in Python) turns on debug logging along with the right-click menu and developer tools. If you have not set up logging yourself, Cornea writes the log to `%LOCALAPPDATA%\Cornea\logs\cornea.log`, a folder every user can write to, and also shows it on screen. If that file cannot be written, the log only appears on screen. When the file reaches 1 MB it is started over, keeping the three previous ones (`cornea.log.1` to `cornea.log.3`). If you already set up logging, or use `--log-file` or `--log-level`, Cornea uses that and creates nothing.

The log starts with the versions and settings in use (no secrets). It shows start-up steps, refused requests, dev-server output and native action names. It never shows the start-up token, cookies, or what your page sends to an action. In Python, `configure_logging("debug", file="my.log")` does the same without debug mode.

## How long does it take to start?

`cornea open web/dist --measure` shows how long start-up took once the first page has loaded. Add `--json-file timings.json` to keep the numbers. In Python, use `run(..., measure=True)` or read `shell.timings`.

## Trying your page in a browser

```bash
cornea serve path/to/your/web/folder
```

prints one line of JSON with an address. Open that address in a browser to try the page without a window. The window buttons still answer, and dialogs report that they are unavailable.

## Security model

| Guarantee | How |
| --- | --- |
| Only your window can use the server | It listens on your own machine on a free port, and every request needs the session cookie |
| The start-up link is one-time | It carries a token that the window exchanges for the cookie, and it expires |
| Other sites are kept out | Requests with the wrong `Host`, or that change something without the right `Origin`, are refused |
| The page gets a short list of native actions | The built-in ones never read or write files: a dialog only returns the path you chose |
| Risky features are opt-in | Opening files, notifications, dropped files, downloads and `--js-api` are all off until you turn them on |
| Developer tools are off | Turn them on with `--devtools`, `--context-menu`, or `--debug` for both |

## Command line

```bash
cornea open --help     # show a window
cornea serve --help    # serve without a window
```

See the [command line reference](https://github.com/coldsofttech/CorneaShell/blob/main/docs/cli-reference.md) for every option.

## Documentation

- [Examples](https://github.com/coldsofttech/CorneaShell/tree/main/examples) (each has its own README)
- [Command line reference](https://github.com/coldsofttech/CorneaShell/blob/main/docs/cli-reference.md)
- [Python API reference](https://github.com/coldsofttech/CorneaShell/blob/main/docs/api-reference.md)
- [How it works](https://github.com/coldsofttech/CorneaShell/blob/main/docs/architecture.md)
- [Troubleshooting](https://github.com/coldsofttech/CorneaShell/blob/main/docs/troubleshooting.md)
- [Packaging an app](https://github.com/coldsofttech/CorneaShell/blob/main/docs/packaging.md)
- [Third-party notices](https://github.com/coldsofttech/CorneaShell/blob/main/docs/third-party-notices.md)

## Development setup

```bash
git clone https://github.com/coldsofttech/CorneaShell.git
cd CorneaShell
uv sync                       # uses Python 3.11, the minimum supported version
uv run pre-commit install --hook-type pre-commit --hook-type post-commit
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

See the [development guide](https://github.com/coldsofttech/CorneaShell/blob/main/docs/development.md) for linting, type checking and releasing.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](https://github.com/coldsofttech/CorneaShell/blob/main/CONTRIBUTING.md) first; every change keeps the security model and comes with tests. Everyone taking part is expected to follow the [Code of Conduct](https://github.com/coldsofttech/CorneaShell/blob/main/CODE_OF_CONDUCT.md). For help, see [SUPPORT.md](https://github.com/coldsofttech/CorneaShell/blob/main/SUPPORT.md).

## Security

Cornea Shell sits between a web page and your computer, so a bug that lets another program or website reach the local server, or lets a page do more than it was allowed to, is a security issue. Please report it privately as described in [SECURITY.md](https://github.com/coldsofttech/CorneaShell/blob/main/SECURITY.md) and do not open a public issue.

## License

Released under the [MIT License](https://github.com/coldsofttech/CorneaShell/blob/main/LICENSE).
