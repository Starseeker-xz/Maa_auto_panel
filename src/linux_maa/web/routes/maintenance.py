from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from linux_maa.state import state_or_idle
from linux_maa.web.sse import state_event_stream
from linux_maa.web.services import WebServices


def create_maintenance_router(services: WebServices) -> APIRouter:
    """Create APIRouter with endpoints for the maintenance API group."""
    router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])
    configs = services.configs
    maintenance = services.maintenance

    @router.get("/current")
    def current_maintenance() -> dict[str, object]:
        return state_or_idle(maintenance.current())

    @router.get("/current/events")
    def current_maintenance_events(request: Request):
        return state_event_stream(request, maintenance.current_response, maintenance.wait_for_change)

    @router.get("/update-info")
    def update_info() -> dict[str, object]:
        try:
            cli_config = configs.read_cli_config().get("data")
            return maintenance.inspect_update_info(cli_config if isinstance(cli_config, dict) else {})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/{kind}")
    def start_maintenance(kind: str) -> dict[str, object]:
        try:
            return maintenance.start(kind).to_dict()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
