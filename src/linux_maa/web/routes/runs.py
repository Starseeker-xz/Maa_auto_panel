from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from linux_maa.maa import MaaRunRequest
from linux_maa.web.sse import state_event_stream
from linux_maa.web.services import WebServices


class StartRunPayload(BaseModel):
    task: str = Field(min_length=1)
    profile: str = Field(default="default", min_length=1)
    log_level: Annotated[int, Field(ge=0, le=3)] = 1


def create_run_router(services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api/runs", tags=["runs"])
    configs = services.configs
    runs = services.runs

    @router.post("")
    def start_run(payload: StartRunPayload) -> dict[str, object]:
        try:
            configs.resolve("tasks", payload.task)
            configs.resolve("profiles", payload.profile)
            state = runs.start(
                MaaRunRequest(
                    task=payload.task,
                    profile=payload.profile,
                    log_level=payload.log_level,
                )
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Selected task/profile not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return state.to_dict()

    @router.get("/current")
    def current_run() -> dict[str, object]:
        return runs.current_response()

    @router.get("/current/events")
    def current_run_events(request: Request):
        return state_event_stream(request, runs.current_response, runs.wait_for_change)

    @router.get("/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        state = runs.get(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return state.to_dict()

    @router.post("/{run_id}/stop")
    def stop_run(run_id: str) -> dict[str, object]:
        try:
            return runs.stop(run_id).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    return router
