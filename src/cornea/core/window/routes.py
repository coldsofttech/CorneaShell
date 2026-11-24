"""HTTP routes that let a frameless UI control its window."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cornea.core.window.window import (
    WINDOW_HEADER,
    WindowController,
    check_limit,
)


class TitleBody(BaseModel):
    """The new window title."""

    title: str = Field(min_length=1, max_length=200)


class CloseBody(BaseModel):
    """Close the window even if the app holds it open."""

    force: bool = False


class GuardBody(BaseModel):
    """Whether the page is busy and wants closing held back."""

    enabled: bool


class EnabledBody(BaseModel):
    """Switch something on or off."""

    enabled: bool


class SizeLimitsBody(BaseModel):
    """The smallest and largest size, each ``[width, height]`` or null for no limit."""

    min_size: tuple[int, int] | None = None
    max_size: tuple[int, int] | None = None


class PositionBody(BaseModel):
    """Where to put the window's top-left corner."""

    x: int
    y: int


class SizeBody(BaseModel):
    """The window's new width and height."""

    width: int
    height: int


def window_for(request: Request) -> WindowController | None:
    """The window the request came from: a child window names itself, otherwise the main one."""
    named = request.headers.get(WINDOW_HEADER)
    if named:
        child: WindowController | None = request.app.state.windows.get(named)
        if child is not None:
            return child
    main: WindowController | None = request.app.state.window
    return main


def _controller(request: Request) -> WindowController:
    controller = window_for(request)
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


def _checked(call: Callable[[], None]) -> dict[str, bool]:
    try:
        call()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/bounds")
def bounds(controller: Controller) -> dict[str, int | None]:
    """The window's ``x``, ``y``, ``width`` and ``height``."""
    return controller.bounds()


@router.post("/always-on-top")
def always_on_top(body: EnabledBody, controller: Controller) -> dict[str, bool]:
    controller.set_always_on_top(body.enabled)
    return {"ok": True}


@router.post("/fullscreen")
def fullscreen(body: EnabledBody, controller: Controller) -> dict[str, bool]:
    controller.set_fullscreen(body.enabled)
    return {"ok": True}


@router.post("/size-limits")
def size_limits(body: SizeLimitsBody, controller: Controller) -> dict[str, bool]:
    """Set the smallest and largest size. A missing or null limit is removed."""
    return _checked(
        lambda: controller.set_size_limits(
            check_limit(body.min_size, "min_size"), check_limit(body.max_size, "max_size")
        )
    )


@router.post("/position")
def set_position(body: PositionBody, controller: Controller) -> dict[str, bool]:
    return _checked(lambda: controller.set_bounds(x=body.x, y=body.y))


@router.post("/size")
def set_size(body: SizeBody, controller: Controller) -> dict[str, bool]:
    return _checked(lambda: controller.set_bounds(width=body.width, height=body.height))
