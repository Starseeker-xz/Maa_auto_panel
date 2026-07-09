from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from linux_maa.maa.runner import MaaRunRequest
from linux_maa.run_manager.router import RunControlRoutes, register_run_control_routes
from linux_maa.web.services import WebServices


class StartRunPayload(BaseModel):
    task: str = Field(min_length=1)
    profile: str = Field(default="default", min_length=1)
    log_level: Annotated[int, Field(ge=0, le=3)] = 1
    retry_count: Annotated[int, Field(ge=1, le=50)] = 1


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
                    retry_count=payload.retry_count,
                )
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Selected task/profile not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return state.to_dict()

    register_run_control_routes(
        router,
        RunControlRoutes(
            manager=runs,
            stop_target="run_id",
            include_get_by_id=True,
        ),
    )

    return router
