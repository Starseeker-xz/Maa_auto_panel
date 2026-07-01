from __future__ import annotations

from fastapi import APIRouter, HTTPException

from linux_maa.web.services import WebServices


def create_maa_router(services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api/maa", tags=["maa"])
    stages = services.stages
    infrast = services.infrast

    @router.get("/stages")
    def maa_stages(client: str = "Official", include_unavailable: bool = False) -> dict[str, object]:
        try:
            return stages.stage_candidates(client=client, include_unavailable=include_unavailable)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/infrast/plans")
    def maa_infrast_plans(filename: str = "") -> dict[str, object]:
        try:
            return infrast.plan_options(filename=filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/infrast/files")
    def maa_infrast_files() -> dict[str, object]:
        try:
            return infrast.file_options()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
