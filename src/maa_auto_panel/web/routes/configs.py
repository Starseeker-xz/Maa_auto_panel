from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from maa_auto_panel.config.manager import ConfigValidationFailure
from maa_auto_panel.utils import relative_path
from maa_auto_panel.web.responses import validation_exception
from maa_auto_panel.web.services import WebServices


class SaveTaskConfigPayload(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    task_items: list[dict[str, Any]] = Field(default_factory=list)


def create_config_router(services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api/configs", tags=["configs"])
    runtime = services.runtime
    configs = services.configs

    @router.get("")
    def list_configs() -> dict[str, object]:
        return {
            "config_root": relative_path(runtime.config_dir, runtime.data_root),
            "profiles": [item.to_dict() for item in configs.list_kind("profiles")],
            "tasks": [item.to_dict() for item in configs.list_kind("tasks")],
        }

    @router.get("/{kind}/{name}")
    def read_config(kind: str, name: str) -> dict[str, object]:
        try:
            if kind == "tasks":
                return configs.read_task_config(name)
            if kind == "profiles":
                return configs.read_profile_config(name)
            info, content = configs.read(kind, name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Config not found") from exc
        return {"file": info.to_dict(), "content": content}

    @router.put("/tasks/{name}")
    def save_task_config(name: str, payload: SaveTaskConfigPayload) -> dict[str, object]:
        try:
            return configs.write_task_config(name, base_data=payload.data, task_items=payload.task_items)
        except ConfigValidationFailure as exc:
            raise validation_exception("Task config validation failed", exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/{kind}/{name}")
    def delete_config(kind: str, name: str) -> dict[str, object]:
        try:
            record = configs.delete(kind, name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Config not found") from exc
        return {"deleted": record.to_dict()}

    return router
