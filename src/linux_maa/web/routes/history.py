from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from linux_maa.web.services import WebServices


def create_history_router(services: WebServices) -> APIRouter:
    """Create APIRouter with endpoints for the history API group."""
    router = APIRouter(prefix="/api/history", tags=["history"])
    run_state = services.run_state
    diagnostics = services.diagnostics

    @router.get("/runs")
    def list_runs(
        kind: Literal["manual", "schedule", "maintenance", "tool"] | None = None,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, object]:
        return {"runs": [run.to_dict() for run in run_state.runs(kind=kind, limit=limit)]}

    @router.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        run = run_state.run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return {
            "run": run.to_dict(),
            "attempts": run_state.attempts(run_id),
            "events": diagnostics.run_events(run_id),
        }

    return router
