# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `Server`, `Security` and `Window` settings, with the context menu and developer tools off unless enabled or in debug mode.
- `create_app()` builds the secured local server app with your routers, a health check and the web source.
- Local server security checks: Host and Origin validation, a one-time start-up link with a session cookie, and security response headers.
- A generated Python API reference, and examples in it and in the command line help and reference.
- Web sources: `Static` bundles, `Url` addresses, and `Asgi`/`Wsgi` apps (WSGI needs the `wsgi` extra).

### Changed

- Renamed the project to Cornea Shell (`cornea-shell`, import `cornea`, command `cornea`).
- The command line options no longer read environment variables.
