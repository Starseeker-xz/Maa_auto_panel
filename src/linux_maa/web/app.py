from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from linux_maa.config import ConfigManager, ConfigValidationFailure, FrameworkSettingsManager
from linux_maa.maa import MaaInfrastService, MaaRunManager, MaaRunRequest, MaaRuntime, MaaStageService, MaintenanceActionManager, find_repo_root
from linux_maa.scheduler import ScheduleConfigManager, SchedulerService


class StartRunPayload(BaseModel):
    task: str = Field(min_length=1)
    profile: str = Field(default="default", min_length=1)
    log_level: Annotated[int, Field(ge=0, le=3)] = 1


class SaveTaskConfigPayload(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    task_items: list[dict[str, Any]] = Field(default_factory=list)


class SaveSettingsPayload(BaseModel):
    framework: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    maa_cli: dict[str, Any] = Field(default_factory=dict)


class CreateSchedulePayload(BaseModel):
    name: str = Field(min_length=1)
    task_config: str | None = None


class SaveSchedulePayload(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class StartSchedulePayload(BaseModel):
    entry_id: str | None = None


def create_app(repo_root: Path | None = None) -> FastAPI:
    runtime = MaaRuntime(repo_root.resolve() if repo_root is not None else find_repo_root())
    configs = ConfigManager(runtime)
    framework_settings = FrameworkSettingsManager(runtime)
    runs = MaaRunManager(runtime)
    maintenance = MaintenanceActionManager(runtime)
    stages = MaaStageService(runtime)
    infrast = MaaInfrastService(runtime)
    schedule_configs = ScheduleConfigManager(runtime, configs)
    scheduler = SchedulerService(runtime, configs, framework_settings, schedule_configs)
    frontend_dist = runtime.repo_root / "frontend" / "dist"
    frontend_assets = frontend_dist / "assets"

    app = FastAPI(title="Linux MAA WebUI")

    @app.get("/", response_class=HTMLResponse)
    def index():
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return MISSING_FRONTEND_HTML

    if frontend_assets.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=frontend_assets), name="assets")

    @app.get("/api/configs")
    def list_configs() -> dict[str, object]:
        return {
            "config_root": str(runtime.config_dir.relative_to(runtime.repo_root)),
            "profiles": [item.to_dict() for item in configs.list_kind("profiles")],
            "tasks": [item.to_dict() for item in configs.list_kind("tasks")],
        }

    @app.get("/api/configs/{kind}/{name}")
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

    @app.put("/api/configs/tasks/{name}")
    def save_task_config(name: str, payload: SaveTaskConfigPayload) -> dict[str, object]:
        try:
            return configs.write_task_config(name, base_data=payload.data, task_items=payload.task_items)
        except ConfigValidationFailure as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Task config validation failed",
                    "validation": exc.result.to_dict(),
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/settings")
    def read_settings() -> dict[str, object]:
        try:
            return _settings_response(configs, framework_settings, maintenance)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Settings source not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/api/settings")
    def save_settings(payload: SaveSettingsPayload) -> dict[str, object]:
        try:
            profile_validation = configs.schema_validator.validate_profile_config(payload.profile)
            if not profile_validation.valid:
                raise ConfigValidationFailure(profile_validation)
            cli_validation = configs.schema_validator.validate_cli_config(payload.maa_cli)
            if not cli_validation.valid:
                raise ConfigValidationFailure(cli_validation)
            framework_settings.write(payload.framework)
            configs.write_profile_config("default", payload.profile)
            configs.write_cli_config(payload.maa_cli)
            return _settings_response(configs, framework_settings, maintenance)
        except ConfigValidationFailure as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Settings validation failed",
                    "validation": exc.result.to_dict(),
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/maintenance/current")
    def current_maintenance() -> dict[str, object]:
        state = maintenance.current()
        return state.to_dict() if state else {"status": "idle", "output": []}

    @app.get("/api/maintenance/update-info")
    def update_info() -> dict[str, object]:
        try:
            cli_config = configs.read_cli_config().get("data")
            return maintenance.inspect_update_info(cli_config if isinstance(cli_config, dict) else {})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/maa/stages")
    def maa_stages(client: str = "Official", include_unavailable: bool = False) -> dict[str, object]:
        try:
            return stages.stage_candidates(client=client, include_unavailable=include_unavailable)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/maa/infrast/plans")
    def maa_infrast_plans(filename: str = "") -> dict[str, object]:
        try:
            return infrast.plan_options(filename=filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/maa/infrast/files")
    def maa_infrast_files() -> dict[str, object]:
        try:
            return infrast.file_options()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/maintenance/{kind}")
    def start_maintenance(kind: str) -> dict[str, object]:
        try:
            return maintenance.start(kind).to_dict()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/schedules")
    def list_schedules() -> dict[str, object]:
        try:
            return scheduler.list_schedules()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/schedules")
    def create_schedule(payload: CreateSchedulePayload) -> dict[str, object]:
        try:
            return scheduler.create_schedule(payload.name, task_config=payload.task_config)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Selected task config not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/schedules/current")
    def current_scheduled_run() -> dict[str, object]:
        state = scheduler.current()
        return state.to_dict() if state else {"status": "idle", "output": []}

    @app.post("/api/schedules/current/stop")
    def stop_scheduled_run() -> dict[str, object]:
        try:
            return scheduler.stop_current().to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="No scheduled run active") from exc

    @app.get("/api/schedules/{schedule_id}")
    def read_schedule(schedule_id: str) -> dict[str, object]:
        try:
            return scheduler.read_schedule(schedule_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Schedule not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/api/schedules/{schedule_id}")
    def save_schedule(schedule_id: str, payload: SaveSchedulePayload) -> dict[str, object]:
        try:
            return scheduler.save_schedule(schedule_id, payload.config)
        except ConfigValidationFailure as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Schedule validation failed",
                    "validation": exc.result.to_dict(),
                },
            ) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Schedule source not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/schedules/{schedule_id}")
    def delete_schedule(schedule_id: str) -> dict[str, object]:
        try:
            return scheduler.delete_schedule(schedule_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Schedule not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/schedules/{schedule_id}/run")
    def start_schedule_now(schedule_id: str, payload: StartSchedulePayload) -> dict[str, object]:
        try:
            return scheduler.start_now(schedule_id, entry_id=payload.entry_id).to_dict()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Schedule not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/configs/{kind}/{name}")
    def delete_config(kind: str, name: str) -> dict[str, object]:
        try:
            record = configs.delete(kind, name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Config not found") from exc
        return {"deleted": record.to_dict()}

    @app.post("/api/runs")
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

    @app.get("/api/runs/current")
    def current_run() -> dict[str, object]:
        state = runs.current()
        return state.to_dict() if state else {"status": "idle", "output": []}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        state = runs.get(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return state.to_dict()

    @app.post("/api/runs/{run_id}/stop")
    def stop_run(run_id: str) -> dict[str, object]:
        try:
            return runs.stop(run_id).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    def frontend_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return MISSING_FRONTEND_HTML

    return app


def _settings_response(
    configs: ConfigManager,
    framework_settings: FrameworkSettingsManager,
    maintenance: MaintenanceActionManager,
) -> dict[str, object]:
    current_maintenance = maintenance.current()
    return {
        "framework": framework_settings.read(),
        "profile": configs.read_profile_config("default"),
        "maa_cli": configs.read_cli_config(),
        "maintenance": current_maintenance.to_dict() if current_maintenance else {"status": "idle", "output": []},
    }


MISSING_FRONTEND_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Linux MAA</title>
</head>
<body>
  <main style="font-family: system-ui, sans-serif; max-width: 720px; margin: 48px auto; line-height: 1.6;">
    <h1>Linux MAA WebUI</h1>
    <p>前端构建产物不存在。请先在 <code>frontend/</code> 中运行 <code>npm install</code> 和 <code>npm run build</code>。</p>
  </main>
</body>
</html>
"""
