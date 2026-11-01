"""Cornea with a FastAPI backend.

Run it in a window:        python examples/fastapi_app/main.py
Or in a browser tab:       python examples/fastapi_app/main.py --headless
Serve the FastAPI app itself: python examples/fastapi_app/main.py --mount
"""

import argparse
import sys
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from cornea import Asgi, Shell, Static, Window, ready_line

WEB = Path(__file__).parent / "web"

# Your own routes. Cornea mounts them under /api, behind the session cookie.
router = APIRouter()


@router.get("/greeting")
def greeting(name: str = "world") -> dict[str, str]:
    return {"message": f"Hello, {name}, from FastAPI!"}


# The same routes as a whole app, for --mount. Cornea owns /api, so here they live at the root.
app = FastAPI()


@app.get("/greeting")
def mounted_greeting(name: str = "world") -> dict[str, str]:
    return greeting(name)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    page = (WEB / "index.html").read_text(encoding="utf-8")
    return page.replace('content="/api/greeting"', 'content="/greeting"')


app.mount("/", StaticFiles(directory=WEB), name="web")


def build_shell(*, headless: bool = False, mount: bool = False) -> Shell:
    window = None if headless else Window(title="FastAPI example", size=(900, 600))
    if mount:
        # Cornea serves the FastAPI app itself instead of a folder plus routers.
        shell = Shell(Asgi("main:app", app_dir=Path(__file__).parent), window=window)
    else:
        shell = Shell(Static(WEB), routers=[router], window=window)

    # A native action: the page calls it with POST /api/bridge/shout.
    @shell.action("shout")
    def shout(text: str) -> str:
        return text.upper()

    return shell


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headless", action="store_true", help="no window; print the address")
    parser.add_argument("--mount", action="store_true", help="serve the FastAPI app itself")
    args = parser.parse_args()
    shell = build_shell(headless=args.headless, mount=args.mount)
    if args.headless:
        # Print the address (it carries the one-time start-up token) and serve until Ctrl+C.
        shell.run(on_ready=lambda ready: sys.stdout.write(ready_line(ready) + "\n"))
    else:
        shell.run()


if __name__ == "__main__":
    main()
