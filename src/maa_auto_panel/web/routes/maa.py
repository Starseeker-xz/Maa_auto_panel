from __future__ import annotations

from fastapi import APIRouter

from maa_auto_panel.web.services import WebServices


def create_maa_router(services: WebServices) -> APIRouter:
    """Create APIRouter with endpoints for the maa API group."""
    router = APIRouter(prefix="/api/maa", tags=["maa"])
    stages = services.stages
    infrast = services.infrast

    @router.get("/stages")
    def maa_stages(client: str = "Official", include_unavailable: bool = False) -> dict[str, object]:
        return stages.stage_candidates(client=client, include_unavailable=include_unavailable)

    @router.get("/infrast/plans")
    def maa_infrast_plans(filename: str = "") -> dict[str, object]:
        return infrast.plan_options(filename=filename)

    @router.get("/infrast/files")
    def maa_infrast_files() -> dict[str, object]:
        return infrast.file_options()

    return router
