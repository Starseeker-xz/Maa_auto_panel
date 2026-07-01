from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from linux_maa.config import ConfigValidationFailure
from linux_maa.web.responses import state_or_idle, validation_exception
from linux_maa.web.services import WebServices


class CreateSchedulePayload(BaseModel):
    name: str = Field(min_length=1)
    task_config: str | None = None


class SaveSchedulePayload(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class StartSchedulePayload(BaseModel):
    entry_id: str | None = None


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

    @router.get("/current")
    def current_scheduled_run() -> dict[str, object]:
        return state_or_idle(scheduler.current())

    @router.post("/current/stop")
    def stop_scheduled_run() -> dict[str, object]:
        try:
            return scheduler.stop_current().to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="No scheduled run active") from exc

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
            return scheduler.start_now(schedule_id, entry_id=payload.entry_id).to_dict()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Schedule not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
