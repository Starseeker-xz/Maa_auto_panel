from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from maa_auto_panel.run_manager.router import RunControlRoutes, register_run_control_routes
from maa_auto_panel.web.services import WebServices


class StartToolPayload(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    retry_count: int = Field(default=1, ge=1, le=50)


def create_tools_router(services: WebServices) -> APIRouter:
    """Create APIRouter with endpoints for the tools API group."""
    router = APIRouter(prefix="/api/tools", tags=["tools"])
    tools = services.tools

    @router.get("")
    def list_tools() -> dict[str, object]:
        return tools.tools_response()

    register_run_control_routes(
        router,
        RunControlRoutes(
            manager=tools,
            stop_target="current",
            current_not_found_detail="No tool run active",
        ),
    )

    @router.post("/{tool_id}/run")
    def start_tool_run(tool_id: str, payload: StartToolPayload) -> dict[str, object]:
        return tools.start(tool_id, payload.config, retry_count=payload.retry_count).to_dict()

    return router
