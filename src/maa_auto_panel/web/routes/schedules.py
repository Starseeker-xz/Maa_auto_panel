from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from maa_auto_panel.config.manager import ConfigValidationFailure
from maa_auto_panel.run_manager.router import RunControlRoutes, register_run_control_routes
from maa_auto_panel.web.responses import validation_exception
from maa_auto_panel.web.services import WebServices


class CreateSchedulePayload(BaseModel):
    name: str = Field(min_length=1)
    task_config: str | None = None


class SaveSchedulePayload(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class StartSchedulePayload(BaseModel):
    entry_id: str | None = None
    retry_count: int = Field(default=1, ge=1, le=50)


def create_schedule_router(services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api/schedules", tags=["schedules"])
    scheduler = services.scheduler

    @router.get("")
    def list_schedules() -> dict[str, object]:
        try:
            return scheduler.list_schedules()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("")
    def create_schedule(payload: CreateSchedulePayload) -> dict[str, object]:
        try:
            return scheduler.create_schedule(payload.name, task_config=payload.task_config)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Selected task config not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    register_run_control_routes(
        router,
        RunControlRoutes(
            manager=scheduler,
            current_not_found_detail="No scheduled run active",
        ),
    )

    @router.get("/{schedule_id}")
    def read_schedule(schedule_id: str) -> dict[str, object]:
        try:
            return scheduler.read_schedule(schedule_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Schedule not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.put("/{schedule_id}")
    def save_schedule(schedule_id: str, payload: SaveSchedulePayload) -> dict[str, object]:
        try:
            return scheduler.save_schedule(schedule_id, payload.config)
        except ConfigValidationFailure as exc:
            raise validation_exception("Schedule validation failed", exc) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Schedule source not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/{schedule_id}")
    def delete_schedule(schedule_id: str) -> dict[str, object]:
        try:
            return scheduler.delete_schedule(schedule_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Schedule not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/{schedule_id}/run")
    def start_schedule_now(schedule_id: str, payload: StartSchedulePayload) -> dict[str, object]:
        try:
            return scheduler.start_now(schedule_id, entry_id=payload.entry_id, retry_count=payload.retry_count).to_dict()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Schedule not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
