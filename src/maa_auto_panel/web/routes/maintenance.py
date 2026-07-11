from __future__ import annotations

from fastapi import APIRouter, HTTPException

from maa_auto_panel.run_manager.router import RunControlRoutes, register_run_control_routes
from maa_auto_panel.web.services import WebServices


def create_maintenance_router(services: WebServices) -> APIRouter:
    """Create APIRouter with endpoints for the maintenance API group."""
    router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])
    configs = services.configs
    maintenance = services.maintenance
    notifications = services.notifications

    register_run_control_routes(
        router,
        RunControlRoutes(
            manager=maintenance.runs,
            expose_stop=False,
            expose_force_stop=False,
        ),
    )

    @router.get("/update-info")
    def update_info() -> dict[str, object]:
        try:
            cli_config = configs.read_cli_config().get("data")
            info = maintenance.inspect_update_info(cli_config if isinstance(cli_config, dict) else {})
            notifications.inspect_runtime_presence()
            notifications.observe_update_info(info)
            return info
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
