# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `Server`, `Security` and `Window` settings, with the context menu and developer tools off unless enabled or in debug mode.
- `cornea open` shows a web bundle, address or app in a window, and `cornea serve` serves it without one, printing the address as a JSON line. Every setting has a flag.
- Native actions your page can call: choose a folder or file, choose where to save, open a link in the browser, and platform info. Register your own with `@shell.action`, and switch individual ones off with `Bridge(disabled=...)`.
- Running without a window (`window=None`) keeps the window controls working against a stand-in window, so a frameless page can be tried in a normal browser. `run(on_ready=...)` and `ready_line()` let tools learn the address.
- A web address (`Url`) opens in the window directly, with your size, title and other window settings; use the normal window frame with it.
- A native window on Windows (pywebview is installed with the package): frameless option, window controls for your own title bar, and the context menu and developer tools off unless you turn them on or use debug mode.
- `Shell` and `run()` start the secured local server on a free port, print nothing that contains the start-up token, and release the port when stopped.
- Web bundles are served with single-page-app routing, correct content types, caching for fingerprinted files, and protection against paths outside the bundle. `Static` can also find a bundle inside an installed package or in `web/dist`.
- `create_app()` builds the secured local server app with your routers, a health check and the web source.
- Local server security checks: Host and Origin validation, a one-time start-up link with a session cookie, and security response headers.
- A generated Python API reference, and examples in it and in the command line help and reference.
- Web sources: `Static` bundles, `Url` addresses, and `Asgi`/`Wsgi` apps (WSGI needs the `wsgi` extra).

### Changed

- Renamed the project to Cornea Shell (`cornea-shell`, import `cornea`, command `cornea`).
- The command line options no longer read environment variables.
