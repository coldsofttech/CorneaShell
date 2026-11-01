# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Show a web UI in a native Windows window, backed by a secured local server, from Python or with the `cornea` command.
- Show a folder of built web files (plain HTML, React and similar), a Python web app (FastAPI, Flask, Django), or a page from a server you already run.
- Keep other programs and web pages on the same machine out: only your window can use the local server.
- Your own Python routes next to the page, called with ordinary `fetch()` requests.
- A frameless window mode, with window controls your page can call to draw its own title bar.
- Native actions your page can call: choose a folder or file, choose where to save, open a link, read platform information, and your own.
- The right-click menu and developer tools are off unless you turn them on, or use debug mode for both.
- `cornea serve` shows a page without a window, so you can try it in a browser, and prints the address as one line of JSON.
- `cornea open --mode proxy` shows a page from a server you already run, such as a Vite dev server, through Cornea, so the page gets Cornea's security, the window controls and a frameless window, and hot reload keeps working. Needs the new `proxy` extra.
- `--csp-profile dev` allows the inline scripts and styles that development servers need. It is for development only.
- Example projects for plain HTML, React, FastAPI, Flask, Django and Node.js, each with a Python script as well as the `cornea` command.
- `cornea open --run "npm run dev" ...` starts your dev server for you and stops it, with everything it started, when the window closes.
- Apps can run one copy at a time, reopen the window where it was, and get their own taskbar identity.
- Frameless windows can show pages Cornea does not serve, if you opt in to give the page the window controls (trusted pages only).
- Windows can have an icon.
- A refused request with the wrong Host or Origin is now reported as a warning, so a wrong `allowed_hosts` setting is no longer silent.
- Settings for the `cornea` command can be kept in `cornea.toml` or in `[tool.cornea]` of `pyproject.toml`.
- Your Python code can send events to the page, and can keep the window open while the app is busy: the page is told and can ask before closing. The page can also set this itself.
- `cornea doctor` shows the versions Cornea runs on and checks that the machine is ready: WebView2, pywebview, a free port, your settings file and the log folder.
- Pages can load one script from Cornea, `/api/client.js`, for the window controls, native actions and `cornea:*` events instead of writing the calls themselves.
- Debug logs now say what the content security policy blocked, and where.
- Downloads are blocked unless you allow them with `--downloads`; the person then chooses where to save each file.
- A guide to packaging an app with PyInstaller, with a test that builds one.
- Windows notifications: `shell.show_notification()` from Python, and the `show_notification` action for a page once you allow it (`--notifications`). Needs `pip install "cornea-shell[notifications]"`.
- Files dropped on the window can be passed to the page (`--drop-files`), and the page can open a file or show it in Explorer (`--open-files`). Both are off by default; programs and scripts are never opened.
- `--measure` (and `measure=True` in Python) shows how long start-up took; the numbers can be saved as JSON. There is a documented target.
- `open` and `serve` show a short summary of what they are about to do.
- Logging for troubleshooting: `--log-level` and `--log-file`, and `--debug` (and debug mode in Python) now turns on debug logging too, writing to your local app data folder if you set nothing up. The start-up token is never written to a log.
- More examples: Vue, HTMX, Streamlit, MkDocs, and .NET, Java, PHP and Go servers, checked weekly by an automated workflow.
