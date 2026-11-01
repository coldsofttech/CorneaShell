"""The HTTP route that lets the page call the native bridge."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from cornea.core.bridge.bridge import ActionRegistry

router = APIRouter(prefix="/bridge", tags=["bridge"])


@router.get("")
def list_actions(request: Request) -> dict[str, list[str]]:
    """The actions the page can call."""
    registry: ActionRegistry = request.app.state.actions
    return {"actions": registry.names()}


@router.post("/{action}", response_model=None)
async def call_action(
    action: str, request: Request, arguments: Annotated[dict[str, Any] | None, Body()] = None
) -> JSONResponse:
    """Run one action with the JSON body as its named arguments."""
    registry: ActionRegistry = request.app.state.actions
    status, payload = await registry.invoke(action, arguments or {}, request.app.state.window)
    return JSONResponse(payload, status_code=status)
