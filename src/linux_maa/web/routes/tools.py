from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from linux_maa.web.sse import state_event_stream
from linux_maa.web.services import WebServices


class StartToolPayload(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


def create_tools_router(services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api/tools", tags=["tools"])
    tools = services.tools

    @router.get("")
    def list_tools() -> dict[str, object]:
        return tools.tools_response()

    @router.get("/current")
    def current_tool_run() -> dict[str, object]:
        return tools.current_response()

    @router.get("/current/events")
    def current_tool_run_events(request: Request):
        return state_event_stream(request, tools.current_response, tools.wait_for_change)

    @router.post("/current/stop")
    def stop_current_tool_run() -> dict[str, object]:
        try:
            return tools.stop_current().to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="No tool run active") from exc

    @router.post("/{tool_id}/run")
    def start_tool_run(tool_id: str, payload: StartToolPayload) -> dict[str, object]:
        try:
            return tools.start(tool_id, payload.config).to_dict()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
