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

## Global notifications and Settings panels

- 新增 `notifications/`：五类稳定 tag、独立 TOML 设置、100 条有界 Toast event broker、runtime condition 去重、run finished listener、外部 sender protocol/空实现。
- 新增 `/api/notifications/settings` GET/PUT 和 `/api/notifications/events` SSE；全局 App `NotificationCenter` 展示最多 4 条、8 秒自动关闭的右下角 Toast。
- runtime 缺失启动检查 maa-cli binary 与 `libMaaCore.so`；runtime 更新通知复用 `/api/maintenance/update-info` 的 maa-cli/MaaCore 结果，不把 hot resource 混入该 tag。
- 手动、自动 schedule、手动触发 schedule 的成功/失败在 run 终态持久化后通知；stopped 过滤；tool/maintenance 未注入 listener。
- Settings 保存 payload 纳入通知策略；`pages/settings/panels.tsx` 现拥有 SettingsPanel、DeviceSettingsPanel、NotificationSettingsPanel，设备/通知展示与修改从页面状态编排中拆出。
- 新增 `tests/test_notifications.py`，覆盖五 tag、设置 round-trip、持续条件去重、三类 run tag、停止过滤和 update 范围。

### Verification

- `.venv/bin/python -m pytest -q`: 81 passed。
- `frontend npm run build`: passed；bundle 771.60 kB，既有 >500 kB warning 仍在。
- `.venv/bin/python -m compileall -q src` 与 `git diff --check`: passed。
- systemd 在四类 run 均 idle 后重启；最终 active。通知设置 API 返回 5 tag，聚合 settings 返回 notifications，首页正常。
- 通知 SSE 实连 17 秒收到 `: keep-alive`；journal 无 traceback/error。
- 一次 exec 工具调用因构造参数时把 `workdir` 误拼入命令字符串导致 JavaScript SyntaxError，未执行任何命令；修正调用后完成验收。
