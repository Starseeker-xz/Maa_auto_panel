# Session: 2026-07-11_0203-separate-runtime-and-agent-doc

- Started: 2026-07-11T02:03:42+00:00
- Task: 审计并将 runtime 从 data 中拆分，补充中文 Agent 项目说明。

## Implementation

- 路径边界改为 application / framework data / integration runtime / disposable cache；新增 `MAA_AUTO_PANEL_RUNTIME_DIR` 与 `--runtime-dir`。
- `MaaInstallation` 默认从 `<app>/runtime/maa` 派生；MAA config 仍保留在 `<data>/config/maa`。
- Docker/Compose/entrypoint/maa-env 同步使用 `/app/runtime` 独立 bind mount。
- 生成配置 artifact 相对 application root 记录，避免 runtime 拆出 data 后产生绝对路径。
- 新增 `docs/AGENT_PROJECT_GUIDE.md`。

## Environment effects

- 在确认 `/api/runs/current` idle 后停止 systemd 服务，将 `data/runtime/maa` 一次性移动到 `runtime/maa`。
- 遗留 `data/runtime/framework/webui.log` 移到 `data/debug/framework/legacy-webui.log`，删除空的旧 `data/runtime`。
- 重启 `maa-auto-panel-webui.service`；最终状态 active，API 返回 idle。

## Verification

- `.venv/bin/python -m pytest -q`: 77 passed。
- `.venv/bin/python -m compileall -q src`: passed。
- `docker compose config --quiet`: passed；未 build/up Docker。
- `git diff --check`: passed。
- `scripts/maa-env maa version`: maa-cli 0.7.5 / MaaCore 6.14.0。
