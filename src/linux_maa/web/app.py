from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from linux_maa.config import ConfigManager
from linux_maa.maa import MaaRunManager, MaaRunRequest, MaaRuntime, find_repo_root


class StartRunPayload(BaseModel):
    task: str = Field(min_length=1)
    profile: str = Field(default="default", min_length=1)
    attempts: Annotated[int, Field(ge=1, le=10)] = 1
    timeout_seconds: Annotated[int, Field(ge=30, le=86400)] = 900
    log_level: Annotated[int, Field(ge=0, le=3)] = 1


def create_app(repo_root: Path | None = None) -> FastAPI:
    runtime = MaaRuntime(find_repo_root(repo_root))
    configs = ConfigManager(runtime)
    runs = MaaRunManager(runtime)
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
            info, content = configs.read(kind, name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Config not found") from exc
        return {"file": info.to_dict(), "content": content}

    @app.post("/api/runs")
    def start_run(payload: StartRunPayload) -> dict[str, object]:
        try:
            configs.resolve("tasks", payload.task)
            configs.resolve("profiles", payload.profile)
            state = runs.start(
                MaaRunRequest(
                    task=payload.task,
                    profile=payload.profile,
                    attempts=payload.attempts,
                    timeout_seconds=payload.timeout_seconds,
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
