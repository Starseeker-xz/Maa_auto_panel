# Project History

Compact handoff state for future sessions. Source session ids on entries.
Confidence: Confirmed / Likely / Hypothesis / Unknown.

---

## Repository State

- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): Path `/root/Linux_maa`, branch `main`. Python ≥3.12, `uv` 管理。CLI 入口 `linux-maa = linux_maa.cli:main`。前端 React + TypeScript + Vite 在 `frontend/`。45 个测试全通过，前端构建正常。
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 已清理所有死兼容模块（4 个顶层 re-export、`maa/logs/` 目录、旧别名、前端死 `translateLogLine`）。当前无遗留 TODO/FIXME/HACK 注释。
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 唯一确认的死代码 `scheduler/store.py`（`ScheduleStore` 别名，零导入）已删除。`translate_maa_cli_log()` 经核实有测试覆盖，保留为合法公共 API。
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 前端 `CONNECTION_TYPES`/`CONNECTION_CONFIGS`/`TOUCH_MODES` 已从 `SettingsPage` 和 `ProfileEditor` 中提取到共享 `lib/constants.ts`。

### 目录结构

| 目录 | 用途 | 纳入版本控制 |
|------|------|:---:|
| `src/linux_maa/` | Python 后端源码（56 文件，约 6,700 行） | ✅ |
| `frontend/src/` | React 前端源码（41 文件，约 5,500–6,000 行） | ✅ |
| `config/` | maa-cli 原生配置 + Linux MAA 框架配置 | ✅ |
| `tests/` | 7 个测试文件，45 个测试 | ✅ |
| `docs/` | 架构文档 + MAA 上游中文文档镜像 | ✅ |
| `state/linux-maa/` | 运行历史、调度器状态（4 个 JSON） | ❌ |
| `debug/linux-maa/` | 框架日志、事件 JSONL、外部进程日志 | ❌ |
| `runtime/maa/` | maa-cli 二进制 + MaaCore 资源 + 运行日志 | ❌ |
| `scripts/` | `maa-env` 环境包装脚本 | ✅ |
| `.codex/` | 项目持久化状态 | ✅ |

---

## Product Direction

- Confirmed (`2026-06-26_1620-maa-cli-framework-docs`): 长期目标：Docker 化 WebUI 框架，围绕 maa-cli/MaaCore 为 redroid 上的明日方舟提供自动化。直接集成 MaaCore 已探索但主路径是调用 maa-cli。
- Confirmed (`2026-06-29_2137-project-state-docs`): 项目仍处于早期阶段。优先简化架构、删除已废弃的回退路径。
- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): 目标体验：类 GUI 的 Web UI，含配置编辑、任务执行、定时执行、实用的重试/恢复行为。

---

## Runtime & Environment

- Confirmed (`2026-06-30_2318-gpu-ocr-research`): `maa-cli v0.7.5` + `MaaCore v6.13.0`。MaaCore 仅含 CPU ONNX Runtime provider，NVIDIA RTX 2080 Ti / Intel iGPU 不可用 GPU OCR。
- Confirmed (`2026-06-30_2056-scheduled-execution`): 默认 profile 目标 ADB `192.168.5.151:5555`，包 `com.hypergryph.arknights.bilibili`，客户端 `Bilibili`。连接 `CompatPOSIXShell`，触控 `MaaTouch`，CPU OCR。
- Confirmed (`2026-07-01_2153-manage-service-history`): WebUI 生命周期临时由 systemd unit `/etc/systemd/system/linux-maa-webui.service` 管理。命令 `uv run linux-maa webui --host 0.0.0.0 --port 8000`，工作目录 `/root/Linux_maa`。已注册、已验证、`disabled`、`inactive`。

---

## Backend Architecture

- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 模块按领域组织，分层清晰：
  - **基础设施**：`utils.py`（工具）、`storage/`（文件 I/O、回收站）、`process.py`（流式子进程）、`state.py`（idle 响应）
  - **领域服务**：`maa/`（运行时、运行编排、关卡/基建选项、维护）、`config/`（配置 CRUD、验证、任务投影）、`scheduler/`（定时配置、策略、脚本、后台循环）、`logs/`（流式翻译器、解析规则、缓冲区）、`game/`（APK 下载安装）、`android/`（ADB 封装）、`tools/`（工具执行器）
  - **Web/API**：`web/`（FastAPI 工厂、SSE 引擎、8 个路由模块）
  - **入口**：`cli.py`（argparse → 4 子命令）、`diagnostics.py`（日志基础设施）、`run_state.py`（持久化状态）、`settings.py`（常量）
- Confirmed (`2026-07-04_0055-modularize-log-pipeline`): WebUI 可见日志系统已破坏性迁移为 source/template/block 管线：
  - `logs/pipeline.py`：通用 `LogPipelineSession`、`LogSourceSpec`、plain/event 模板，负责 source 注册、流切分、ANSI/`\r`/`\b` 处理、block 维护。
  - `logs/records.py`：单一 block-shaped `LogEntry` 和 `LogMessage`；旧 `line`/`task`/`summary` union 不再输出。
  - `logs/state.py`：`RunLogBuffer` 有界缓存，汇总 `log_entries`、`output`，并委托模板投影 `task_results` 与 current block elapsed。
  - `maa/log_templates.py`：MAA 专用 task lifecycle、summary、git output、招募/基建/掉落翻译；task 相关状态不在通用 pipeline 内。
  - 原始 stdout/stderr 保存仍归 `Diagnostics`，未并入可见日志管线。
- Confirmed (`2026-07-03_0105-audit-log-module`): `process.py` 中的 `run_streaming_process()` 是通用流式子进程原语，保留原始回车符供翻译器折叠终端重绘输出（如 tqdm）。
- Confirmed (`2026-07-01_2153-manage-service-history`): 状态与诊断分离：
  - **状态**（`state/linux-maa/`）：可读 JSON（运行记录、尝试、统计、触发器）
  - **诊断**（`debug/linux-maa/`）：可丢弃（`framework.log`、事件 JSONL、外部日志按源分组）
  - 旧 `runtime/linux-maa/scheduler.sqlite3` 已删除，无迁移

---

## API Surface

- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): API 路由 8 组：
  - `/api/configs` — 配置文件 CRUD
  - `/api/runs` — 手动运行启停/状态/SSE
  - `/api/schedules` — 定时配置 CRUD + 运行/停止
  - `/api/settings` — 框架设置读写
  - `/api/maintenance` — 维护动作 + 更新检查
  - `/api/history` — 历史运行记录
  - `/api/maa` — 关卡 + 基建排班选项
  - `/api/tools` — 工具列表 + 运行/状态/SSE

---

## Core Features

### 任务配置与编辑
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): `linux_maa.managed_params` 架构：保存时为托管参数（数组、关卡、排班）写 runtime placeholder，运行时解析为 maa-cli 可识别的真实值。
- Confirmed (`2026-06-30_0124-config-save-delete`): 配置删除走 `.trash` 回收站，非硬删除。
- Confirmed (`2026-06-30_0124-config-save-delete`): 主界面选中任务配置应以 URL 为唯一来源，不要引入重复本地状态。
- Confirmed (`2026-07-02_1933-config-sync-ui-schema`): 前端 `task-editor-schemas/*.json` 仅影响 UI 可见字段，不影响后端读写。删 schema 键时同步删模板 `general`/`advanced` 列表。

### 手动运行
- Confirmed (`2026-06-30_1752-maa-cli-sequential-analysis`): 上游 maa-cli 在一个 `Assistant` 实例中运行所有子任务。手动 WebUI 运行是单发的，不再有 WebUI 级 timeout/retry loop。
- Confirmed (`2026-07-01_1506-sse-log-delta`): 运行状态使用一次全量快照 + SSE 增量 patch（`replace_from/items`）。`LogPane` 在用户在底部时自动跟随，向上滚动时停止跟随。

### 定时执行
- Confirmed (`2026-06-30_2056-scheduled-execution`): 定时执行使用 `SchedulerService`（后台线程），策略引擎支持 `important`、`unlimited_runs`、`min_daily_successes`、`retry_even_success`。
- Confirmed (`2026-07-03_0105-audit-log-module`): 定时脚本 hook 通过 `run_streaming_process()` 执行，stdout/stderr 流入可见日志。

### 工具页面
- Confirmed (`2026-07-02_2245-tools-page`): `ToolRunManager` 驱动可插拔工具。初始注册工具 `game-update`。工具运行复用共享 RunLogBuffer + SSE patch 模式。运行中/停止中状态拒绝新启动。

- Confirmed (`2026-07-04_0055-modularize-log-pipeline`): `RunLogBuffer` 的 `log_entries`、`task_results`、`output` 仍有界，但 `log_entries` 现在统一为 `type="block"`、`kind=line|task|summary|event` 的单一结构。前端不再兼容旧 `line`/`task`/`summary` union。
- Confirmed (`2026-07-04_0055-modularize-log-pipeline`): MAA 任务生命周期、summary、关卡信息、掉落/家具、招募结果、基建换班、Git fetch/update 输出分组在 `maa/log_templates.py`；通用 `logs/` 模块只处理 source/template 管线和终端控制字符。
- Confirmed (`2026-07-04_0055-modularize-log-pipeline`): scheduler child timeout 使用 `current_block_elapsed_seconds(kind="task")`。`task_results` 由 MAA task-kind block 投影，task 状态不属于通用 pipeline。
- Confirmed (`2026-07-04_0055-modularize-log-pipeline`): stdout 资源变化块只由 `Already up to date.` 或 `Updating <sha>..<sha>` 开始，并以 `Summary` 为边界；stderr 的 `From https://github.com/...` 是单独资源 fetch 诊断块，不属于 stdout 资源变化规则。已有回归测试覆盖。
- Confirmed (`2026-07-04_0055-modularize-log-pipeline`): 统一日志块不再保存在 `state/`。`state/linux-maa/run-history/scheduled-run-attempts.json` 只是 attempt 索引，包含 `log_entries_file`；实际日志块历史保存在 `history/linux-maa/runs/`：
  - `schedules/<schedule-id>/<run-id>.json`
  - `manual/<run-id>.json`
  - `tools/<tool-id>/<run-id>.json`
  - `maintenance/<kind>/<run-id>.json`
  `RunStateStore.attempts(run_id)` 会从 history 文件回填 `log_entries`。
- Confirmed (`2026-07-02_2144-manual-stop-delay`): maa-cli 日志到 stderr，`--log-file` 会导致 stderr 丢失 info 生命周期日志。当前不再传 `--log-file`。

---

## Frontend Architecture

- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 路由结构：
  - `/` → `MainPage`（三栏：任务列表 / 配置编辑 / 日志）
  - `/tasks/:taskConfig` 和 `/tasks/:taskConfig/items/:taskItemId`
  - `/schedule` 和 `/schedule/:scheduleId` → `SchedulePage`
  - `/tools` → `ToolsPage`（三栏：工具列表 / 配置 / 日志）
  - `/settings` → `SettingsPage`
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 共享组件：`FormFields`、`DirtyActions`、`ConfirmDialog`、`InsertionLine`、`PrimitiveArrayEditor`、`ProfileEditor`、8 个 shadcn/ui 组件。
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 库文件：`api.ts`（集中 API）、`types.ts`（480 行类型）、`runStream.ts`（SSE 处理）、`jsonformsRenderers.tsx`（410 行自定义渲染器）、`taskWorkspace.ts`、`usePolling.ts`、`theme.ts` 等。

---

## Known Risks & Active Issues

### 未解决问题
- Confirmed (`2026-07-02_2144-manual-stop-delay`): **ADB 冷启动 60 秒延迟**。MaaCore 在无本地 ADB server 时 `adb devices` 耗时 60s。`kill_adb_on_exit = true` 使每次运行后复发。热 ADB 环境同一连接路径 < 1s。建议：启动前 `adb start-server` + `adb connect`，考虑 `kill_adb_on_exit = false`。
- Confirmed (`2026-06-30_2318-gpu-ocr-research`): **GPU OCR 不可用**。当前 MaaCore 仅含 CPU ONNX Runtime。升级 MaaCore 后需重新测试。

### 架构风险
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): `scheduler/service.py`（760 行）是后端最大单文件，应拆分。
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): `SettingsPage.tsx`（700+ 行）承载三组设置，应拆卡片。
- Confirmed (`2026-07-01_2153-manage-service-history`): `JSON.stringify` dirty 比较（ConfigEditorPane、SchedulePage、SettingsPage）当前可接受，若用户自由编辑 JSON 需换 stable deep equal。
- Confirmed (`2026-07-01_2153-manage-service-history`): 前端 bundle 500 kB chunk warning，后续可用 lazy routes 优化。
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 前端 `CONNECTION_TYPES`/`TOUCH_MODES` 常量在 `SettingsPage` 和 `ProfileEditor` 中重复定义。

### 数据管理
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): `runtime/maa/run-logs/`（52 个日志）和 `generated-configs/`（45 个配置）量较大，建议定期清理或加自动保留策略。
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): `.codex/conversations/` 中 25 个会话记录，其中 16 个任务已完成可归档，8 个含活跃引用，1 个为空目录。

---

## Documentation

- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 根目录文档：
  - `README.md` — 项目介绍与开发指南
  - `BACKEND_AUDIT.md` — 后端审计报告（session `2026-06-30_2342-full-project-audit`）
  - `FRONTEND_AUDIT.md` — 前端审计报告（同上）
  - `PROJECT_AUDIT.md` — 综合审计报告（本轮新增）
  - `PROJECT_EXECUTION_POLICY.md` — 项目执行方针
- Confirmed (`2026-06-29_2137-project-state-docs`): 架构或工作流变更时应同步更新 `README.md`、`docs/README.md`、`docs/maa-runtime.md`、`docs/architecture-direction.md`、`.codex/project-history.md`、`.codex/project-lessons.md`。

---

## Latest Verification

- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): `uv run python -m compileall -q src tests` ✅
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): `uv run pytest -q` — 45 tests pass ✅
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): `cd frontend && npm run build` — pass (existing Vite chunk warning only) ✅
- Confirmed (`2026-07-03_0105-audit-log-module`): `systemd-analyze verify` pass, `systemctl is-enabled` returns `disabled`, port 8000 free ✅
