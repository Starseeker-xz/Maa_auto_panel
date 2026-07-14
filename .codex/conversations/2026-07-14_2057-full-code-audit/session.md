# Session 2026-07-14_2057-full-code-audit

## Scope

- 完整审计后端、前端、测试、依赖与持久状态。
- 重点检查重复逻辑、过度实现、死代码、硬编码和 integration 通用化边界。
- 重写前后端审计的当前架构与活跃问题；精简 project history/lessons/conversation index；归档失效会话；调整 `AGENTS.md`。
- 前端只读审计由子代理 `frontend-audit` 执行，详细证据见 `frontend-audit.md`。

## Baseline and verification

- 工作开始时 tracked worktree clean；本会话目录是唯一新增项。
- `.venv/bin/python -m pytest -q`: 142 passed in 7.71s；coverage run 142 passed in 10.03s。
- coverage: 7602 statements，2002 missed，74%；data file 为 `scratch/.coverage`。
- `.venv/bin/python -m compileall -q src`: passed。
- `frontend/npm run build`: passed；入口 416.61 kB / gzip 133.22 kB，editor 289.90 kB / gzip 94.29 kB。
- `npm audit --omit=dev`: 0 vulnerabilities（前端子代理执行）。
- `uvx vulture src tests --min-confidence 80`: no findings。
- `uvx ruff check src tests`: 11 errors；notifications unused `Path`，contracts 9 个 unresolved `RunAttempt/RunCallbackAPI`，manager unresolved `Callable`。
- `typing.get_type_hints(GenericRunManager.__init__)` 与 `get_type_hints(RunCallbacks)` 均稳定复现 `NameError`。
- 前端 `tsc --noUnusedLocals --noUnusedParameters` 只发现 SchedulePage 未使用 `cn` import。

## Durable audit conclusions

- 后端无 P0。P1 为 scheduler exact-minute missed trigger、APK manifest corrupt overwrite/身份验证不足、shutdown resource-wait 状态语义、open retry 无 checkpoint，以及 scheduler stats 与 retry persistence 非幂等提交边界。
- 手动/定时 MAA callbacks 重复 task session/collector/capture/retry summary，应在 MAA 领域抽 `MaaAttemptExecutor`，不下沉到通用 manager。
- contracts 含无生产调用方的 before_attempt/on_finish/after_run/after_retry/next_command 等扩展点；after_attempt 收到由 decision 伪造而非真实 process result。项目未发布，应删除推测性扩展或按真实第二 integration 重建。
- strict/tolerant log-template loader 共享 item parser 但仍是双轨 container traversal，新增 schema 时易漂移；应统一 error policy。
- 前端 P1 为 tool 过滤 run 后错误开放第二次 start、task editor registry 前端硬编码、跨主路由草稿丢失、无测试。P2 包括四份 SSE 生命周期、LogPane 反解析中文日志、重复 Profile fields、半实现 Tool descriptor、动态 Select 无 fallback、notification Set 无界和 sidebar invalidation。
- 可直接删除/并入的后端 tests 仅约 2–4 个；重点应是共享 fixtures/table-driven cases，并补 scheduler/runner/updater 覆盖，不以低于 100 cases 为目标。

## Files changed

- 重写 `docs/BACKEND_AUDIT.md`：完整系统架构、运行/日志/持久化/部署边界、分级问题、测试审计和实施顺序。
- 重写 `docs/FRONTEND_AUDIT.md`：完整前端架构、组件库复用判断、分级问题和实施顺序。
- 修改 `AGENTS.md`：明确审计/history/conversation 分工、会话保留含义、兼容层原则和测试精简准则。
- 重写 `.codex/project-history.md`、`.codex/project-lessons.md`、`.codex/conversations/index.md`。
- 保留项目会话：本会话、ADB 冷启动原始复现、容器 SONAME 探索、GUI tools 上游探索、raw log template 覆盖审计。
- 将其余 21 个完成/被覆盖会话移至 `~/.codex/archived_sessions/maa-auto-panel/`；归档总数变为 60。

## Environment effects

- 创建本会话目录与 coverage data；`uv run --with coverage` 临时解析 coverage tool，未修改项目依赖或 lock。
- `frontend/dist` 被 build 刷新，但目录为 ignored build artifact。
- 未修改产品代码，未重启 systemd，未运行 Docker、MAA 或设备任务。
- 会话归档是持续有效的环境整理；追溯路径为 `~/.codex/archived_sessions/maa-auto-panel/`。

## Mistakes / discarded paths

- 首次 `uvx --from coverage coverage run -m pytest` 使用隔离环境，因没有 pytest 失败；改用 `uv run --with coverage`，既加载项目依赖又不写入 pyproject/lock。
- 最终组合验证从仓库根运行 `npm run build`，因 `package.json` 位于 `frontend/` 而 ENOENT；后端 142 tests 已先通过，随后在正确的 `frontend/` cwd 单独重跑构筑。
- 旧审计与 project history 不再作为当前代码事实来源；本轮结论均重新核对当前源码和可执行验证。
