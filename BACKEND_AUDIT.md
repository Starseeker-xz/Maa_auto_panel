# 后端审计报告

Session: `2026-06-30_2342-full-project-audit`

审计范围：`src/linux_maa/` 全部 Python 模块、`config/maa/` 与 `config/linux-maa/` 当前配置、`tests/` 现有测试。基线验证在本轮修正前通过：`uv run python -m compileall -q src tests`、`uv run pytest -q`、`frontend npm run build`。

## 总体结论

后端已经具备上线试用的主体能力：配置读写、任务参数投影、maa-cli 执行、日志翻译、维护动作、动态 Fight/Infrast 选项、定时执行与 SQLite 状态记录都能串起来。主要问题不是单点不可用，而是 AI 迭代常见的“功能能跑但模块边界漂移”：HTTP route、运行状态、路径/slug/版本比较/原子写等基础工具在多处重复实现，后续继续扩展时容易产生分叉。

本轮后端已实施一轮低风险结构修正：拆分 Web API route、抽出 Web 服务组装、统一 idle response、统一 slug/path/atomic-write/version/dict 等小工具，并补充回归测试。没有改变既有公开 API 路径、主要请求体和响应结构。

## 模块结构

### CLI 与兼容入口

- `src/linux_maa/cli.py`
  - CLI 子命令：
    - `update-game`
    - `get-download-link`
    - `run-maa-task`
    - `webui`
  - 只做参数解析和分发，结构清晰。
- ~~`src/linux_maa/adb.py`、`constants.py`、`game_update.py`、`maa_runner.py`~~
  - 已删除 (`2026-07-03_1926-project-review`)：兼容 re-export 模块，全局零引用。

### ADB 与游戏更新

- `src/linux_maa/android/adb.py`
  - `ADBDevice` 封装 `adb -s <serial>`、连接检查、版本号读取、安装、pull。
  - 当前是同步阻塞 CLI 工具，不与 WebUI 强耦合。
- `src/linux_maa/game/update.py`
  - 负责 Bilibili API 查询、APK/增量补丁缓存、下载、安装、校验。
  - 已将 manifest 保存改为原子写，降低中途中断导致缓存状态损坏的风险。
  - 仍缺少网络/ADB fake 测试，属于后续可补项。

### Runtime 与 MAA 执行

- `src/linux_maa/maa/runtime.py`
  - `MaaRuntime` 集中描述 repo、runtime、config、state、scheduler DB 等路径。
  - `env()` 统一提供 maa-cli 运行环境。
- `src/linux_maa/maa/process.py`
  - `run_maa_cli_process()` 是当前 manual/scheduled run 共用的 subprocess/tail/timeout 原语。
  - 这是正确抽象，应继续保持为执行层边界。
- `src/linux_maa/maa/runner.py`
  - CLI 粗重试 `run_maa_task()`。
  - WebUI manual run 的 `MaaRunManager`。
  - `prepare_maa_cli_task()` 负责读取任务配置、选择子任务、投影框架 metadata、生成 runtime JSON，并为 maa-cli 构造临时配置目录。
  - 已统一 task 文件解析、slug、生成文件原子写、相对路径显示，并删除无效 `seen` 变量。

### 配置与任务投影

- `src/linux_maa/config/manager.py`
  - 统一管理 `config/maa/profiles`、`config/maa/tasks`、`config/maa/cli.toml`。
  - 提供文件列表、结构化读取、任务 item 解析、保存、删除到 trash。
  - 已统一命名校验、路径解析、slug、原子写、相对路径显示。
- `src/linux_maa/config/tasks.py`
  - 负责 `linux_maa` metadata 与 maa-cli 原生配置之间的投影。
  - 关键逻辑：
    - 保存时把 managed array、Fight stage、Infrast plan 写为 runtime placeholder。
    - 运行时把 placeholder 解析为 maa-cli 可识别的真实值。
    - 无法解析的子任务会被禁用并写入预处理日志。
  - 当前逻辑集中且合理，但 `MaaStageService`/`MaaInfrastService` 是运行时延迟导入，后续如果继续扩展 handler，建议注册表化。
- `src/linux_maa/config/schema.py`
  - 对 maa-cli task/profile/cli schema 和 Linux MAA metadata schema 做校验。
  - 当前 metadata schema 已包含 scheduling 字段和 managed params。
- `src/linux_maa/config/app_settings.py`
  - 管理 `config/linux-maa/settings.toml`。
  - 已统一原子写和路径显示。

### MAA 动态服务

- `src/linux_maa/maa/logs.py`
  - 状态化 maa-cli 日志翻译器。
  - 能按任务生命周期分组，处理 summary，支持 expected task sequence 来区分重复任务类型。
  - 当前测试覆盖较好。
- `src/linux_maa/maa/stages.py`
  - Fight stage 候选列表，复刻 MAA GUI 的可选关卡规则。
  - 已统一版本解析/比较、dict guard、相对路径显示。
  - 服务方法仍直接返回 API-shaped dict，后续可拆成 domain dataclass + API serializer。
- `src/linux_maa/maa/infrast.py`
  - 基建排班文件与 plan 选项。
  - 当前排班文件使用非跨午夜区间或手动拆分区间，现有 `start <= current <= end` 足够覆盖当前数据。
  - 若以后允许 `"23:00" -> "06:00"` 这种单条跨午夜 period，需要补判断。
- `src/linux_maa/maa/maintenance.py`
  - maa update/hot-update/self-update 动作、当前版本和远端版本检查。
  - 已统一版本比较与 dict guard。
  - 维护动作仍自行管理 subprocess 状态，和 run manager 有相似结构，后续可抽象成通用 action manager。

### Scheduler

- `src/linux_maa/scheduler/models.py`
  - schedule、entry、retry、timeouts、restart、task policy、daily stats dataclass。
  - `slug()` 对外保留，但内部已统一到共享 `slugify()`。
- `src/linux_maa/scheduler/config.py`
  - schedule TOML 读写、默认 schedule 创建、删除到 trash。
  - 已统一原子写、路径显示、文件名校验和 bounded int。
- `src/linux_maa/scheduler/policy.py`
  - 纯策略层：初始选择、重试选择、剩余 slot 判断。
  - 当前测试覆盖了重要 retry 语义，结构较好。
- `src/linux_maa/scheduler/time.py`
  - 游戏日、服务器 reset、本地时区、时间排序。
  - 与 settings 的时区解析存在相近逻辑，但一个返回 `TimezoneInfo`，一个返回 `tzinfo`。暂未强行合并，后续可抽 `timezone_utils.py`。
- `src/linux_maa/scheduler/store.py`
  - SQLite 表：scheduled_runs、scheduled_attempts、daily_task_stats、scheduled_triggers。
  - 当前 SQL 集中，读写边界清楚。
- `src/linux_maa/scheduler/scripts.py`
  - restart script 变量解析和执行。
  - 已统一路径显示和文件名校验。
- `src/linux_maa/scheduler/service.py`
  - 定时服务的 orchestration 层：后台 loop、due entry 检查、run 创建、attempt/retry、脚本 hook、日志、持久化。
  - 已修复 `create_schedule()` 中显式 `task_config` 可能被条件表达式优先级吞掉的问题。
  - 仍是后端最大单文件，应作为下一轮后端重构重点。

### Web API

原先所有 route 和服务创建都在 `src/linux_maa/web/app.py` 中。本轮已拆分：

- `src/linux_maa/web/app.py`
  - 仅负责创建 `FastAPI`、挂载 API router、服务前端静态产物、SPA fallback。
- `src/linux_maa/web/services.py`
  - `WebServices` dataclass 集中创建 runtime/config/settings/run/maintenance/stage/infrast/scheduler 服务。
- `src/linux_maa/web/responses.py`
  - Web 层 validation exception helper。
- `src/linux_maa/web/routes/configs.py`
  - `/api/configs`
  - `/api/configs/{kind}/{name}`
  - `PUT /api/configs/tasks/{name}`
  - `DELETE /api/configs/{kind}/{name}`
- `src/linux_maa/web/routes/settings.py`
  - `GET/PUT /api/settings`
- `src/linux_maa/web/routes/maintenance.py`
  - `/api/maintenance/current`
  - `/api/maintenance/update-info`
  - `POST /api/maintenance/{kind}`
- `src/linux_maa/web/routes/maa.py`
  - `/api/maa/stages`
  - `/api/maa/infrast/files`
  - `/api/maa/infrast/plans`
- `src/linux_maa/web/routes/schedules.py`
  - `/api/schedules`
  - `/api/schedules/current`
  - `/api/schedules/current/stop`
  - `/api/schedules/{schedule_id}`
  - `/api/schedules/{schedule_id}/run`
- `src/linux_maa/web/routes/runs.py`
  - `/api/runs`
  - `/api/runs/current`
  - `/api/runs/{run_id}`
  - `/api/runs/{run_id}/stop`

OpenAPI smoke 已确认上述路径仍挂载。

## 共享工具修正

新增：

- `src/linux_maa/utils.py`
  - `slugify`
  - `dict_value`
  - `write_text_atomic`
  - `relative_path`
  - `validate_file_name`
  - `resolve_existing_named_file`
  - `bounded_int`
  - `extract_version`
  - `version_key`
  - `is_newer_version`
- `src/linux_maa/state.py`
  - `idle_response`
  - `state_or_idle`

替换范围：

- config manager/settings
- schedule config/models/scripts/service
- maa runner/stages/infrast/maintenance
- game update manifest 写入
- Web route current/idle response

## 发现并修复的问题

1. `web/app.py` 过度集中
   - 问题：服务创建、所有 route、Pydantic payload、异常映射、settings response、SPA fallback 混在 349 行文件中。
   - 修复：拆为 services + routes，`app.py` 只保留 app factory 和前端 fallback。

2. 基础工具重复实现
   - 问题：slug、路径解析、相对路径显示、原子写、dict guard、版本解析/比较在多个模块重复。
   - 修复：新增 `utils.py`，替换已确认重复点。

3. idle response 重复
   - 问题：`{"status": "idle", "output": []}` 在 Web 和 scheduler 多处硬编码。
   - 修复：新增 `state.py`，Web 和 scheduler 使用 `state_or_idle()`。

4. schedule 创建时显式 `task_config` 的优先级问题
   - 问题：`task_config or configs[0].name if configs else ""` 会在配置列表为空时丢掉显式传入的 `task_config`。
   - 修复：改为 `task_config or (configs[0].name if configs else "")`，并补测试。

5. runner 中无效变量
   - 问题：`select_task_items()` 中 `seen` 被写入但没有读取。
   - 修复：删除该变量。

6. 缓存 manifest 非原子写
   - 问题：游戏下载 manifest 直接 `write_text`，中断时可能写坏。
   - 修复：改为 `write_text_atomic()`。

## 剩余风险与建议

1. `scheduler/service.py` 仍承担过多职责
   - 当前 600+ 行，包含 loop、run lifecycle、attempt/retry、脚本 hook、日志、持久化。
   - 下一轮建议拆出：
     - `ScheduledRunExecutor`
     - `ScheduleDueChecker`
     - `AttemptRecorder`
     - `RunLogAppender` 或通用 run state helper

2. service 返回值仍偏 API-shaped
   - `MaaStageService`、`MaaInfrastService`、`MaintenanceActionManager.inspect_update_info()`、`SchedulerService._schedule_response()` 直接产出 HTTP JSON 结构。
   - 当前可接受，但如果未来要接 CLI/bot/通知系统，应先拆 domain model 和 serializer。

3. 维护动作和 manual/scheduled run 状态管理相似
   - 三者都包含 state、lock、process、output、done/status 更新。
   - 本轮未做大抽象，避免影响运行路径。后续可抽轻量 `ProcessActionManager`。

4. FastAPI route 测试仍是 smoke 级别
   - 由于项目历史中记录 TestClient 依赖坑，本轮没有引入 TestClient。
   - 后续若补 `httpx2` 或确认当前依赖可用，应加 route 行为测试：404/400/409/422、settings 保存、schedule 保存。

5. 当前配置里 scheduler 是启用状态
   - `config/linux-maa/settings.toml` 当前 `framework.scheduler.enabled = true`。
   - 这与较早项目历史中的“禁用”记录不一致。启动真实 WebUI 时后台 scheduler 会工作，应按当前事实更新项目历史。

## 本轮验证

- `uv run python -m compileall -q src tests`：通过。
- `uv run pytest -q`：25 个测试通过。
- FastAPI OpenAPI smoke：确认 `/api/configs`、`/api/settings`、`/api/maintenance/current`、`/api/maa/stages`、`/api/schedules/current`、`/api/runs/current` 等路径仍挂载。

---

## Post-Audit Changes（审计后变更，session `2026-07-03_1200-audit-and-refactor-codex`）

以下变更发生在原始审计之后，本文件部分描述已过时：

### 已删除模块
- ~~`src/linux_maa/adb.py`、`constants.py`、`game_update.py`、`maa_runner.py`~~ — 兼容 re-export
- ~~`src/linux_maa/maa/logs/`~~ — 兼容导出目录
- ~~`MaaLogMessage`、`MaaSummaryLogRecord`、`MaaTaskLogRecord`、`MaaCliLogTranslator`~~ — 兼容别名

### 模块位置变更
- 日志翻译从 `maa/logs.py` 提升为顶级包 `logs/`（translator、rules、translation、records、state）
- 子进程原语从 `maa/process.py` 提升为顶级 `process.py`
- 运行状态持久化从 SQLite `scheduler/store.py` 迁移至 `run_state.py`（JSON 文件）
- `scheduler/store.py` 现为死代码（`ScheduleStore = RunStateStore` 别名，零导入）

### 新增模块
- `logs/` 包（6 文件）、`tools/` 包（2 文件）、`process.py`、`run_state.py`
- `web/sse.py`（SSE 引擎）、`web/routes/tools.py`、`web/routes/history.py`
- `scheduler/scripts.py`

### 当前测试数：45（原 25）

