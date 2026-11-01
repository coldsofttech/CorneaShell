# Packaging

How to turn a Cornea app into a program people can install without Python. This uses
[PyInstaller](https://pyinstaller.org/).

What was tested: a one-folder build (`--onedir`) of a small app, built with PyInstaller 6.22 on
Python 3.11, started without a window and asked for its page and `/api/client.js`
(`tests/test_packaging.py`, run by the examples workflow). A real window, a one-file build
(`--onefile`), an installer and code signing were not tested here, so treat those parts as advice.

## 1. Find your files from the frozen program

A frozen program does not have your source tree. Files added with `--add-data` are unpacked into a
folder named by `sys._MEIPASS`. Use it for your web folder and your icon:

```python
import sys
from pathlib import Path

from cornea import Shell, Static, Window

base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

shell = Shell(
    Static(base / "web"),
    window=Window(title="My App", icon=base / "icon.ico"),
)
shell.run()
```

Do not write next to the program: it usually sits in `Program Files`, which a normal user cannot
write to. Cornea keeps its own files (remembered window, logs) under `%LOCALAPPDATA%\Cornea`.

## 2. Build

```bash
pip install pyinstaller          # or: uv sync --group packaging in this repository
pyinstaller --noconfirm --onedir --windowed --name MyApp ^
  --icon icon.ico ^
  --add-data "web;web" --add-data "icon.ico;." ^
  --collect-submodules uvicorn ^
  --collect-data cornea ^
  app.py
```

(`^` continues a line in `cmd`; use a backtick in PowerShell.) The result is the folder
`dist\MyApp`, with `MyApp.exe` inside.

| Flag | Why |
| --- | --- |
| `--add-data "web;web"` | Your built web files. The text after `;` is the folder inside the package. |
| `--collect-submodules uvicorn` | uvicorn picks its HTTP and WebSocket parts by name at run time, so PyInstaller cannot see them. |
| `--collect-data cornea` | Cornea's own data file, the script served at `/api/client.js`. |
| `--windowed` | No console window. Nothing printed is visible then, so for problems use `--log-file` or debug mode (see the logging section of the README). |
| `--hidden-import yourmodule` | Needed when you pass the app by name, such as `Asgi("yourmodule:app")` or `Wsgi("yourmodule:app")`, because PyInstaller cannot see a module that is only named in a string. Passing the app object itself, `Asgi(app)`, avoids it. |

pywebview, which shows the window, comes with its own PyInstaller hook. If the window does not
open from the frozen program, add `--collect-all webview` and try again. Extras are found the
normal way when imported by your code: `proxy` needs `httpx` and `websockets`, `notifications`
needs the `winrt` packages.

## 3. The WebView2 runtime

The window needs the Microsoft Edge WebView2 runtime. Windows 11 has it. Windows 10 may not, and
Cornea then stops with a message that names the download page. Your installer should install it:
run Microsoft's Evergreen bootstrapper (`MicrosoftEdgeWebview2Setup.exe /silent /install`) before
the first start. `cornea doctor` shows whether it is there.

## 4. One folder or one file

`--onedir` starts fast and works well inside an installer (Inno Setup, WiX, or MSIX). `--onefile`
packs everything into one program, but unpacks it to a temporary folder on every start, which adds
to the start-up time. Measure it with `--measure` before choosing, and keep the target in the
[architecture guide](architecture.md#startup-time) in mind.

## 5. Signing and antivirus

An unsigned program can be blocked by Smart App Control, company policy or antivirus. This was seen
while testing this guide on one machine: the freshly built program was refused once and ran on the
next try. Sign the program and the installer with a code signing certificate before you ship them.

## 6. Check it

1. Start the built program on a machine without Python.
2. Run `cornea doctor` on a developer machine to rule out missing parts there.
3. If something is wrong, run the program with debug mode on and read the log in
   `%LOCALAPPDATA%\Cornea\logs`.
