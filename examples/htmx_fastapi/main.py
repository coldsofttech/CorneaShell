"""HTMX with FastAPI templates: the server answers with pieces of HTML.

Run it in a window:        python examples/htmx_fastapi/main.py
Or in a browser tab:       python examples/htmx_fastapi/main.py --headless
Needs the examples group:  uv sync --group examples
"""

import argparse
import itertools
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cornea import Asgi, Shell, Window, ready_line

HERE = Path(__file__).parent

app = FastAPI()
templates = Jinja2Templates(directory=HERE / "templates")
counter = itertools.count(1)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.get("/greeting", response_class=HTMLResponse)
def greeting(request: Request, name: str = "world") -> HTMLResponse:
    return templates.TemplateResponse(request, "greeting.html", {"name": name})


@app.post("/count", response_class=HTMLResponse)
def count(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "count.html", {"count": next(counter)})


def build_shell(*, headless: bool = False) -> Shell:
    window = None if headless else Window(title="HTMX example")
    return Shell(Asgi("main:app", app_dir=HERE), window=window)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headless", action="store_true", help="no window; print the address")
    args = parser.parse_args()
    shell = build_shell(headless=args.headless)
    if args.headless:
        shell.run(on_ready=lambda ready: sys.stdout.write(ready_line(ready) + "\n"))
    else:
        shell.run()


if __name__ == "__main__":
    main()
