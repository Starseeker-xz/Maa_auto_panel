from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from linux_maa.web.routes import (
    create_config_router,
    create_maa_router,
    create_maintenance_router,
    create_run_router,
    create_schedule_router,
    create_settings_router,
)
from linux_maa.web.services import create_services


def create_app(repo_root: Path | None = None) -> FastAPI:
    services = create_services(repo_root)
    frontend_dist = services.runtime.repo_root / "frontend" / "dist"
    frontend_assets = frontend_dist / "assets"

    app = FastAPI(title="Linux MAA WebUI")
    app.include_router(create_config_router(services))
    app.include_router(create_settings_router(services))
    app.include_router(create_maintenance_router(services))
    app.include_router(create_maa_router(services))
    app.include_router(create_schedule_router(services))
    app.include_router(create_run_router(services))

    @app.get("/", response_class=HTMLResponse)
    def index():
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return MISSING_FRONTEND_HTML

    if frontend_assets.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=frontend_assets), name="assets")

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
