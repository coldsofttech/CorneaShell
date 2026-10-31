"""Cornea with a FastAPI backend.

Run it in a window:        python examples/fastapi_app/main.py
Or in a browser tab:       python examples/fastapi_app/main.py --headless
"""

import sys
from pathlib import Path

from fastapi import APIRouter

from cornea import Shell, Static, Window, ready_line

WEB = Path(__file__).parent / "web"

# Your own routes. Cornea mounts them under /api, behind the session cookie.
router = APIRouter()


@router.get("/greeting")
def greeting(name: str = "world") -> dict[str, str]:
    return {"message": f"Hello, {name}, from FastAPI!"}


def build_shell(*, headless: bool = False) -> Shell:
    window = None if headless else Window(title="FastAPI example", size=(900, 600))
    shell = Shell(Static(WEB), routers=[router], window=window)

    # A native action: the page calls it with POST /api/bridge/shout.
    @shell.action("shout")
    def shout(text: str) -> str:
        return text.upper()

    return shell


def main() -> None:
    headless = "--headless" in sys.argv
    shell = build_shell(headless=headless)
    if headless:
        # Print the address (it carries the one-time start-up token) and serve until Ctrl+C.
        shell.run(on_ready=lambda ready: sys.stdout.write(ready_line(ready) + "\n"))
    else:
        shell.run()


if __name__ == "__main__":
    main()
