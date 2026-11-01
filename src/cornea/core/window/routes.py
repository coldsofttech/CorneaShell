"""HTTP routes that let a frameless UI control its window."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cornea.core.window.window import WindowController


class TitleBody(BaseModel):
    """The new window title."""

    title: str = Field(min_length=1, max_length=200)


class CloseBody(BaseModel):
    """Close the window even if the app holds it open."""

    force: bool = False


class GuardBody(BaseModel):
    """Whether the page is busy and wants closing held back."""

    enabled: bool


def _controller(request: Request) -> WindowController:
    controller: WindowController | None = request.app.state.window
    if controller is None:
        raise HTTPException(status_code=409, detail="There is no window to control.")
    return controller


Controller = Annotated[WindowController, Depends(_controller)]
router = APIRouter(prefix="/window", tags=["window"])


@router.get("")
def window_state(controller: Controller) -> dict[str, Any]:
    """The window's title and whether it is maximized or minimized."""
    return controller.state()


@router.post("/minimize")
def minimize(controller: Controller) -> dict[str, bool]:
    controller.minimize()
    return {"ok": True}


@router.post("/maximize")
def maximize(controller: Controller) -> dict[str, bool]:
    controller.maximize()
    return {"ok": True}


@router.post("/restore")
def restore(controller: Controller) -> dict[str, bool]:
    controller.restore()
    return {"ok": True}


@router.post("/close")
def close(
    controller: Controller, body: Annotated[CloseBody | None, Body()] = None
) -> dict[str, bool]:
    """Close the window. If the app holds it open this answers ``blocked`` unless ``force``."""
    if controller.close(force=body.force if body else False):
        return {"ok": True}
    return {"ok": False, "blocked": True}


@router.post("/close-guard")
def close_guard(body: GuardBody, request: Request) -> dict[str, bool]:
    """Let the page say it is busy (``enabled``), so closing the window is held back."""
    request.app.state.close_guard.page_holds = body.enabled
    return {"ok": True, "enabled": body.enabled}


@router.post("/title")
def set_title(body: TitleBody, controller: Controller) -> dict[str, bool]:
    controller.set_title(body.title)
    return {"ok": True}
