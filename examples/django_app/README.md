# Django

![Cornea Shell](https://img.shields.io/badge/Cornea%20Shell-0.1-0A7EA4?logo=windows&logoColor=white) ![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white) ![Django](https://img.shields.io/badge/Django-ASGI-092E20?logo=django&logoColor=white) ![JavaScript](https://img.shields.io/badge/JavaScript-ES%20modules-F7DF1E?logo=javascript&logoColor=white) [![CI](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/CorneaShell/actions/workflows/ci.yml)

A whole Django site in one file, mounted in the same process as Cornea.

**You need:** Django (`uv sync --group examples`, or `pip install django`).

## Create this kind of app

Cornea mounts Django through its ASGI entry point. Two Django-specific things matter:

1. **`ALLOWED_HOSTS`** must accept the local address Cornea serves on: `["127.0.0.1", "localhost"]`.
2. **Static files**: Django's development static serving is not used. Serve your own JavaScript from a view, as this example does for `app.js`, or collect static files into a folder and give that folder to Cornea with `Static(...)`.

A full project works the same way: point Cornea at the `application` object in your `asgi.py`.

```bash
django-admin startproject mysite
cd mysite
# in mysite/settings.py: ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
```

```bash
uv run cornea open --asgi mysite.asgi:application --app-dir path/to/mysite
```

This example avoids a project folder: `settings.configure(...)` and a `urlpatterns` list in `django_example.py` make a complete site, and `application = get_asgi_application()` ends the file.

## Run it

### With the command line

```bash
uv run cornea open --asgi django_example:application --app-dir examples/django_app --title "Django"
```

### With the Python package

```bash
uv run python examples/django_app/main.py
```

```python
from cornea import Asgi, Shell

Shell(Asgi("django_example:application", app_dir="examples/django_app")).run()
```

The same entry point takes `--headless` (no window; it prints an address to open in a browser).

## Using Cornea features

Cornea answers under `/api` (and `/health`) on the same address as your page, so the page reaches it with plain `fetch()` calls. Add Cornea's one small script to the page your Django view returns (the `PAGE` string in `django_example.py`):

```html
<script src="/api/client.js"></script>
```

It defines `window.cornea`. Dialogs and your own actions work straight away; opening files, notifications, dropped files and downloads are off until you allow them.

### Your own actions (Python only)

An action is a Python function the page can call. Register it on the shell:

```python
shell = Shell(Asgi("django_example:application", app_dir="examples/django_app"))


@shell.action("shout")
def shout(text: str) -> str:
    return text.upper()


shell.run()
```

```javascript
const result = await cornea.call("shout", { text: "hello" });   // "HELLO"
```

The command line cannot register actions, because they are Python code. From the command line you get the built-in ones: `choose_folder`, `choose_file`, `save_file`, `open_external` and `platform_info`. Switch one off with `--disable-action NAME`.

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
uv run cornea open --asgi django_example:application --app-dir examples/django_app --notifications
```

To show a toast from a Django view, hand the module a callback that `main.py` fills in once the shell exists:

```python
notify = lambda title, message: None  # django_example.py: replaced by main.py


def finished(request):
    notify("Export finished", "3 files were saved.")
    return JsonResponse({"ok": True})
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
uv run cornea open --asgi django_example:application --app-dir examples/django_app --open-files --drop-files --downloads
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

Django's CSRF middleware is off in this example (`MIDDLEWARE=[]`). If you turn it on, send the CSRF token with page requests as usual; Cornea's own `/api` calls do not use it.
