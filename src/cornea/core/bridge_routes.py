"""The HTTP route that lets the page call the native bridge."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from cornea.core.bridge import ActionRegistry, BadArguments, UnknownAction
from cornea.core.window import Unavailable

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bridge", tags=["bridge"])


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


@router.get("")
def list_actions(request: Request) -> dict[str, list[str]]:
    """The actions the page can call."""
    registry: ActionRegistry = request.app.state.actions
    return {"actions": registry.names()}


@router.post("/{action}", response_model=None)
async def call_action(
    action: str, request: Request, arguments: Annotated[dict[str, Any] | None, Body()] = None
) -> JSONResponse:
    """Run one action with the JSON body as its named arguments.

    A dialog that cannot be shown (no window) answers ``available: false``; it is not an error.
    """
    registry: ActionRegistry = request.app.state.actions
    try:
        result = await registry.call(action, arguments or {}, request.app.state.window)
    except UnknownAction:
        return _error(404, "Unknown action")
    except BadArguments as exc:
        return _error(422, str(exc))
    except Unavailable as exc:
        return JSONResponse({"available": False, "reason": str(exc)})
    except ValueError as exc:
        return _error(422, str(exc))
    except Exception:
        # The details stay in the log: the page is not told how the host's code failed.
        logger.exception("The action %r failed", action)
        return _error(500, "The action failed")
    return JSONResponse({"available": True, "result": jsonable_encoder(result)})
