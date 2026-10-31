# Cornea Shell

[![CI](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cornea-shell)](https://pypi.org/project/cornea-shell/)
[![Python versions](https://img.shields.io/pypi/pyversions/cornea-shell)](https://pypi.org/project/cornea-shell/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/github/license/coldsofttech/CorneaShell)](LICENSE)

Show a web UI in a native Windows window, backed by a secured local server. You bring the UI, whether it is plain HTML, a React build, a Flask or Django site, or a page from a Node server. Cornea handles the window, the local security and the bridge to native features.

## What you get

- **A native window** on the Microsoft Edge WebView2 engine, with an optional frameless mode so your page draws its own title bar.
- **A secured local server.** Only your window can use it: other programs and web pages on the same machine are kept out.
- **Any web UI.** A folder of built files, a Python web app, or an address you already run.
- **Your own Python routes** next to the UI, called with ordinary `fetch()`.
- **Native actions your page can call:** choose a folder or file, choose where to save, open a link in the browser, read platform info, and your own.
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

To run Flask or Django apps (WSGI), add the extra: `pip install "cornea-shell[wsgi]"`.

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
| A dev server that is already running (Vite, Next.js, Node) | the address: `cornea open http://localhost:5173` |
| A FastAPI or Django (ASGI) app | `cornea open --asgi myproject.asgi:application --app-dir .` |
| A Flask or Django (WSGI) app | `cornea open --wsgi myapp:app --app-dir .` |

An address you already run is shown as it is. Cornea does not serve it, so it is not behind Cornea's security, and it needs the normal window frame.

Every one of these is a small, runnable project in [examples](examples).

## A frameless window with your own title bar

Run with `--frameless` and draw the title bar in your page. The buttons call Cornea:

```javascript
await fetch("/api/window/minimize", { method: "POST" });
await fetch("/api/window/maximize", { method: "POST" });
await fetch("/api/window/close", { method: "POST" });
```

Give the empty part of your bar the class `pywebview-drag-region` so it drags the window. `GET /api/window` tells your page whether the window is frameless, so it can draw the bar only when needed.

## Trying your page in a browser

```bash
cornea serve path/to/your/web/folder
```

prints one line of JSON with an address. Open that address in a browser to try the page without a window. The window buttons still answer, and dialogs report that they are unavailable.

## Security in short

- The server listens on your own machine only, on a free port.
- The first address carries a one-time token. The window exchanges it for a session cookie, and nothing else can reach the server without that cookie.
- Requests from other sites, and requests that change something without the right `Origin`, are refused.
- The page can only use a short list of native actions, plus any you add yourself. The built-in ones never read or write files: a dialog only returns the path you chose.
- The right-click menu and developer tools are off. Turn them on with `--devtools`, `--context-menu`, or `--debug` for both.

## Command line

```bash
cornea open --help     # show a window
cornea serve --help    # serve without a window
```

See the [command line guide](docs/cli.md) for every option.

## More

- [Examples](examples)
- [Command line guide](docs/cli.md) and [reference](docs/cli-reference.md)
- [Python API reference](docs/api-reference.md)
- [How it works](docs/architecture.md)

## Development

```bash
git clone https://github.com/coldsofttech/CorneaShell.git
cd CorneaShell
uv sync
uv run pytest
```

See the [development guide](docs/development.md) for linting, type checking and releasing.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Please report security issues privately as described in [SECURITY.md](SECURITY.md).

## License

Released under the [MIT License](LICENSE).
