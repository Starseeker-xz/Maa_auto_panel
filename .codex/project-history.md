# Project History

Compact handoff state for future sessions. Source session ids on entries.
Confidence: Confirmed / Likely / Hypothesis / Unknown.

---

## Repository State

- Confirmed (`2026-07-04_1305-unify-run-log-sse`): Path `/root/Linux_maa`, branch `main`. Python ≥3.12, `uv` 管理。CLI 入口 `linux-maa = linux_maa.cli:main`。前端 React + TypeScript + Vite 在 `frontend/`。当前测试规模 48 个，前端构建正常。
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 已清理所有死兼容模块（4 个顶层 re-export、`maa/logs/` 目录、旧别名、前端死 `translateLogLine`）。当前无遗留 TODO/FIXME/HACK 注释。
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 唯一确认的死代码 `scheduler/store.py`（`ScheduleStore` 别名，零导入）已删除。`translate_maa_cli_log()` 经核实有测试覆盖，保留为合法公共 API。
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 前端 `CONNECTION_TYPES`/`CONNECTION_CONFIGS`/`TOUCH_MODES` 已从 `SettingsPage` 和 `ProfileEditor` 中提取到共享 `lib/constants.ts`。
- Confirmed (`2026-07-04_1115-review-cleanup`): 后端内部兼容/便利 re-export 导入已清理；`config`、`maa`、`logs`、`scheduler`、`storage`、`tools`、`tools.game`、`android`、`web` 包级 `__init__.py` 不再转发具体对象，内部代码改为从定义模块直接导入。`linux_maa.tools.game` 包仍保留为 `python -m linux_maa.tools.game` 入口，`ToolRunManager` 命令拼接不受影响。
- Confirmed (`2026-07-04_1115-review-cleanup`): 前端清理了确认未使用的导出/类型面：`FieldLabel`、`TaskEditorTemplate`、多项仅内部引用的 API 响应子类型改为非导出，删除未用 `CardFooter` 和未用 `SchedulePage.refreshDetail()`；`ScrollBar` 保留为 `ScrollArea` 内部实现但不再导出。
- Confirmed (`2026-07-04_clone-maa-sources`): 已将 MAA 和 maa-cli 上游源码浅克隆到 `external/`（已加入 `.gitignore`）：
  - `external/MaaAssistantArknights/` — MAA 主仓库（C++，含 MaaCore、resource、docs、tools）
  - `external/maa-cli/` — maa-cli 仓库（Rust，含 CLI crates、schemas、安装脚本）
- Confirmed (`2026-07-04_clone-maa-sources`): 已完成 MAA GUI 日志面板与截图机制分析，详见 `external/MAA_GUI_ANALYSIS.md`。核心发现：
  - 日志：双层模型（卡片+条目），语义颜色（非级别颜色），`AsstMsg` → `AddLog` 流程，卡片拆分规则
  - 截图：回调只传 JSON 不含图像，图像通过独立 API (`AsstGetImage`) 拉取；缩略图按需附加、调试截图落盘
  - 对 Linux MAA 参考价值：图像与回调分离是刚性约束，maacore 回调不可能直接给截图

### 目录结构

| 目录 | 用途 | 纳入版本控制 |
|------|------|:---:|
| `src/linux_maa/` | Python 后端源码（56 文件，约 6,700 行） | ✅ |
| `frontend/src/` | React 前端源码（41 文件，约 5,500–6,000 行） | ✅ |
| `config/` | 本地 maa-cli 原生配置 + Linux MAA 框架配置（手动测试会改动） | ❌ |
| `tests/` | 7 个测试文件，50 个测试 | ✅ |
| `docs/` | 架构文档 + MAA 上游中文文档镜像 | ✅ |
| `state/linux-maa/` | 运行历史、调度器状态（4 个 JSON） | ❌ |
| `history/linux-maa/runs/` | WebUI 可见日志块历史 JSON | ❌ |
| `debug/linux-maa/` | 框架日志、事件 JSONL、外部进程日志 | ❌ |
| `runtime/maa/` | maa-cli 二进制 + MaaCore 资源 + 运行日志 | ❌ |
| `scripts/` | `maa-env` 环境包装脚本 | ✅ |
| `external/` | 克隆的第三方源码（MAA、maa-cli）供参考 | ❌ |
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
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 本轮运行/SSE/history 重构后已重启 `linux-maa-webui.service`。unit 仍为 `disabled` 但当前 `active (running)`，监听 `0.0.0.0:8000`，`/api/settings` 本机 curl 正常；最近确认时间为 2026-07-04 21:21 UTC 后。
- Confirmed (`2026-07-05_1823-check-history-chunking`): 修复定时 run `f7ecfac6dafc` 暴露的 task 分块和停止状态问题后，已在 2026-07-05 18:37 UTC 重启 `linux-maa-webui.service`。服务当前 active，`/api/schedules/current` 返回 idle，`/api/schedules/daily-test` 中 `f7ecfac6dafc` 持久状态为 `stopped`。
- Confirmed (`2026-07-05_1926-inspect-concurrency`): 新增全局 ADB 设备运行仲裁后已重启 `linux-maa-webui.service`。服务当前 active，`/api/settings` 本机 curl 正常。

---

## Backend Architecture

- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): 模块按领域组织，分层清晰：
  - **基础设施**：`utils.py`（工具）、`storage/`（文件 I/O、回收站）、`process.py`（流式子进程）、`state.py`（idle 响应）
  - **领域服务**：`maa/`（运行时、运行编排、关卡/基建选项、维护）、`config/`（配置 CRUD、验证、任务投影）、`scheduler/`（定时配置、策略、脚本、后台循环）、`logs/`（流式翻译器、解析规则、缓冲区）、`game/`（APK 下载安装）、`android/`（ADB 封装）、`tools/`（工具执行器）
  - **Web/API**：`web/`（FastAPI 工厂、SSE 引擎、8 个路由模块）
  - **入口**：`cli.py`（argparse → 4 子命令）、`diagnostics.py`（日志基础设施）、`run_state.py`（持久化状态）、`settings.py`（常量）
- Confirmed (`2026-07-04_0341-log-template-framework`): WebUI 可见日志系统已破坏性迁移为通用 source/block-rule 管线：
  - `logs/pipeline.py`：通用 `LogPipelineSession`、`LogSourceSpec`、`BlockDefinition`、`ActiveBlock`；负责 source 注册、流切分、ANSI/`\r`/`\b` 处理、每 source 唯一 active block、`matched_end|superseded|passive_boundary|flush` 关闭原因和 fallback 行块。
  - `logs/records.py`：单一 block-shaped `LogEntry` 和 `LogMessage`；`kind` 是开放字符串，`status` 是通用 `BlockStatus`（含 `default`、`warning`）。
  - `logs/state.py`：`RunLogBuffer` 有界缓存，汇总 `log_entries` 和 `output`，但不再拥有 `task_results`。
  - `maa/log_templates.py`：MAA 侧只注册 block definitions/source defaults 和翻译 hooks；summary、git output、招募/基建/掉落翻译仍在此模块，task lifecycle/result 逻辑已移出。
  - 原始 stdout/stderr 保存仍归 `Diagnostics`，未并入可见日志管线。
- Confirmed (`2026-07-03_0105-audit-log-module`): `process.py` 中的 `run_streaming_process()` 是通用流式子进程原语，保留原始回车符供翻译器折叠终端重绘输出（如 tqdm）。
- Confirmed (`2026-07-01_2153-manage-service-history`): 状态与诊断分离：
  - **状态**（`state/linux-maa/`）：可读 JSON（运行记录、重试索引、统计、触发器）
  - **诊断**（`debug/linux-maa/`）：可丢弃（`framework.log`、事件 JSONL、外部日志按源分组）
  - 旧 `runtime/linux-maa/scheduler.sqlite3` 已删除，无迁移
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 手动、定时、工具、维护运行已统一为 `LiveRun` + `LiveRetry` 运行结构（`src/linux_maa/run_executor.py`）。Run 顶层使用 `started_at`/`updated_at`/`ended_at`、`max_retries`、`retry_count`、`log_files`，不再使用旧 `created_at`、顶层 `log_file` 或旧 attempt API。
- Confirmed (`2026-07-05_1926-inspect-concurrency`): 新增共享运行仲裁器 `src/linux_maa/run_coordinator.py`。手动 Maa、定时 Maa、工具运行通过同一个 `RunCoordinator` 声明 ADB 设备占用；冲突检测目前只按提交的连接地址判断 `adb-device` 资源。优先级：自动定时最高、手动触发定时其次、普通手动/工具相同。低优先级遇到高优先级占用返回 409；同优先级等待释放；高优先级会请求低优先级运行停止，并通过该运行自己的 stop/force-stop 回调和 stop-kill 阈值完成抢占。维护动作当前不声明 ADB 资源。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): `RunStateStore` 历史索引改为 `state/linux-maa/run-history/run-retries.json`；历史文件为 `{"run": ..., "retries": [...]}`。每个 retry 持有 `log_entries`、`task_results`、`closed`、`updated_at`、`log_entries_file`，实际可见日志仍写到 `history/linux-maa/runs/**/<run-id>.json`。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 可见日志块 `LogEntry` 增加 `updated_at` 和 `closed`；当前 retry 的 `RunLogBuffer` 会在 retry seal 时 flush/close，结束后的 retry 不再更新。SSE patch 只对 `retries` 做列表补丁，run 顶层状态通过嵌套 `run` patch 更新。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): task success/failure 已从可见日志系统剥离。`process.run_streaming_process()` 支持 raw line callback；manual/scheduled Maa callers 用 `MaaTaskResultCollector` 只消费 `maa-cli:stderr` 原始行来生成 retry-local `task_results`。`LogPipelineSession` 不再有 task projection API；task sequence hook 在 `2026-07-05_1823-check-history-chunking` 作为 display-only task block 命名能力恢复。
- Confirmed (`2026-07-05_1823-check-history-chunking`): 可见日志 task block 与策略用 `task_results` 已重新解耦清楚：`MaaTaskResultCollector` 仍是 manual/scheduled retry/final-status 的权威来源；`RunLogBuffer.begin_task_sequence()` 只给 `maa-task-lifecycle` 可见日志块提供 task id/name/source_name，用于把 `StartUp`/`Infrast` 等生命周期和详情行聚合成 UI task block，不再恢复旧 projected `task_results`。

---

## API Surface

- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): API 路由 8 组：
  - `/api/configs` — 配置文件 CRUD
  - `/api/runs` — 手动运行启停/强停/状态/SSE
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
- Confirmed (`2026-06-30_1752-maa-cli-sequential-analysis`): 上游 maa-cli 在一个 `Assistant` 实例中运行所有子任务。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 手动 Maa 运行支持页面本地 `retry_count`，每次 retry 重新生成只包含待重试子任务的临时 maa-cli task config；已成功的子任务会在后续 retry 中跳过。`retry_count = 1` 时前端不显示 retry 分段标记。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 手动运行 timeout 由 `framework.run_timeouts` 配置：无输出警告/强停、运行时长警告/强停、停止等待警告/强停。`POST /api/runs/{run_id}/stop` 先请求优雅停止，`POST /api/runs/{run_id}/force-stop` 请求强制 kill；前端停止按钮在 `stopping` 后切换为红色强停按钮。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 运行状态使用一次全量快照 + SSE 增量 patch；payload 与历史结构一致，形如 `{run, retries}`。`LogPane` 从 `retries[].log_entries` 渲染；`max_retries <= 1` 时不显示 retry 分段标记，`max_retries > 1` 时每个 retry 前显示简化标记。

### 定时执行
- Confirmed (`2026-06-30_2056-scheduled-execution`): 定时执行使用 `SchedulerService`（后台线程），策略引擎支持 `important`、`unlimited_runs`、`min_daily_successes`、`retry_even_success`。
- Confirmed (`2026-07-03_0105-audit-log-module`): 定时脚本 hook 通过 `run_streaming_process()` 执行，stdout/stderr 流入可见日志。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 定时执行保留 schedule-specific 策略/状态管理在 `SchedulerService` 内；每次 retry 使用独立 `LiveRetry`、独立可见日志缓存、独立 MaaCore `asst.log` delta。重启脚本 hook 输出写入当前 retry；跳过 run 也会 sealed retry，避免历史日志为空。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 定时执行旧 6 个子任务/整组时限已删除，改为 schedule 中的通用 timeout：`no_output_warning_seconds`、`no_output_kill_seconds`、`runtime_warning_seconds`、`runtime_kill_seconds`、`stop_warning_seconds`、`stop_kill_seconds`。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 定时执行 retry policy 使用 `max_retries`、`buffer_every_retries`、`buffer_seconds`。缓冲语义是每完成 N 次 retry 且仍需继续 retry 时等待 M 秒；总 retry 次数不需要是 N 的倍数。

### 工具页面
- Confirmed (`2026-07-02_2245-tools-page`): `ToolRunManager` 驱动可插拔工具。初始注册工具 `game-update`。工具运行支持页面本地 `retry_count`、通用 SSE patch、`framework.run_timeouts` 和 force-stop。运行中/停止中状态拒绝新启动。

### 维护页面
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 维护动作（MaaCore/resource/maa-cli update）已改为 `max_retries = 1` 的 `LiveRun`/`LiveRetry`，并新增 `/api/maintenance/current/events` SSE；设置页维护 panel 复用通用 `LogPane`，平时隐藏在右栏下方，不再走无 SSE 的独立输出面板。

- Confirmed (`2026-07-04_0341-log-template-framework`): `RunLogBuffer` 的 `log_entries` 和 `output` 仍有界；`log_entries` 统一为 `type="block"` 的单一结构，`kind` 不再限制为固定前端 union。前端不再兼容旧 `line`/`task`/`summary` union。
- Confirmed (`2026-07-04_0341-log-template-framework`): MAA 任务生命周期、summary、关卡信息、掉落/家具、招募结果、基建换班、Git fetch/update 输出分组在 `maa/log_templates.py`；通用 `logs/` 模块只处理 source/block-rule 管线、fallback 行块、metadata 覆写和终端控制字符。
- Superseded (`2026-07-04_1305-unify-run-log-sse`): 旧 scheduler child timeout（基于 active task block elapsed）已删除；当前 timeout 统一为无输出/总运行时长/停止等待三类阈值。
- Confirmed (`2026-07-04_1003-audit-log-pipeline`): 新增中性 `theme` log tone，仅用于主题色结构高亮，不代表重要性；用于当前理智、开始行动、summary 掉落标题/编号/合计等。`Use N medicine` / `Use N expiring medicine` 翻译为理智药/临期理智药并用 warning tone 便于观察。
- Superseded (`2026-07-04_1305-unify-run-log-sse`): 旧 `finish_generic_run()` 已删除。当前 `finish_run()` 同步 `history/linux-maa/runs/**/<run-id>.json` 顶层 `run` 快照，retry history 通过 `add_retry()` 写入。
- Confirmed (`2026-07-04_1003-audit-log-pipeline`): scheduler final status now considers remaining enabled slots for important finite daily-success tasks, matching retry policy. If a finite important task is unmet but can be deferred because enough later slots remain, the current run can still finish `succeeded`. Existing local run `e94016514899` was corrected to overall `succeeded`; attempt records remain unchanged.
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): `LogPane` supports generic live/history rendering from `{run, retries}`. Schedule history loads `/api/history/runs/{run_id}` and renders `retries[].log_entries`; old flattening of `attempts[].log_entries` is gone.
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 前端时间展示统一走 `frontend/src/lib/time.ts`；API/SSE 请求携带浏览器时区，后端新生成的可见日志时间为带 offset 的服务器本地 ISO。Log entry 生命周期字段为 `opened_at`/`sealed_at`，run/retry 仍用 `started_at`/`ended_at`。手动、定时、工具页面共用 `RunStopButton`，`stopping` 后显示红色 force-stop 动作。定时近期运行列表支持删除历史记录，并用徽标区分 `manual` 与定时触发。
- Confirmed (`2026-07-04_1003-audit-log-pipeline`): Fixed scheduler stop deadlock. `SchedulerService.stop_current()` held a non-reentrant lock and called `_append_framework_event()`, which re-entered the lock via `_mark_log_updated()`, causing `/api/schedules` to hang. Scheduler lock is now `RLock`; startup recovery marks persisted `running`/`stopping` records as `stopped`.
- Confirmed (`2026-07-04_0055-modularize-log-pipeline`): stdout 资源变化块只由 `Already up to date.` 或 `Updating <sha>..<sha>` 开始，并以 `Summary` 为边界；stderr 的 `From https://github.com/...` 是单独资源 fetch 诊断块，不属于 stdout 资源变化规则。已有回归测试覆盖。
- Superseded (`2026-07-04_1305-unify-run-log-sse`): 旧 `scheduled-run-attempts.json` / `RunStateStore.attempts()` 结构已移除。当前 `state/linux-maa/run-history/run-retries.json` 是 retry 索引，包含 `log_entries_file`；实际日志块历史保存在 `history/linux-maa/runs/`：
  - `schedules/<schedule-id>/<run-id>.json`
  - `manual/<run-id>.json`
  - `tools/<tool-id>/<run-id>.json`
  - `maintenance/<kind>/<run-id>.json`
  `RunStateStore.retries(run_id)` 会从 history 文件回填当前 retry 的 `log_entries`。
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
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): `scheduler/service.py`（780 行）仍是后端最大单文件，应拆分。
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): `SettingsPage.tsx`（700+ 行）承载三组设置，应拆卡片。
- Confirmed (`2026-07-01_2153-manage-service-history`): `JSON.stringify` dirty 比较（ConfigEditorPane、SchedulePage、SettingsPage）当前可接受，若用户自由编辑 JSON 需换 stable deep equal。
- Confirmed (`2026-07-01_2153-manage-service-history`): 前端 bundle 500 kB chunk warning，后续可用 lazy routes 优化。
- Resolved (`2026-07-04_1305-unify-run-log-sse`): 调度器 retry/final-status 决策不再依赖 WebUI visible-log pipeline 投影出的 `task_results`；manual/scheduled Maa runs 通过 `MaaTaskResultCollector` 从 raw `maa-cli:stderr` 行生成结果，UI 日志模板只负责渲染文本。

### 已解决/决策
- Confirmed (`2026-07-04_1047-audit-log-pipeline-audit`): `config/maa/`、`config/linux-maa/`、`history/` 已加入 `.gitignore`；已用 `git rm --cached` 从索引移除现有配置和运行历史文件，保留本地文件供手动测试。
- Confirmed (`2026-07-04_1047-audit-log-pipeline-audit`): MAA 模板本地 metadata status parser 和 `tone_for_status()` 已支持 `warning`，新增回归测试。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 旧停止语义回归已修复：通用 `run_streaming_process()` 支持 stop warning/kill、显式 force-stop kill、运行时长 warning/kill、无输出 warning/kill。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 旧 bounded attempt cursor 丢日志问题已通过 retry-local `RunLogBuffer` 移除；每个 retry 只写自己的 `log_entries`/`task_results`，不再从 run-level 有界缓存切片。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 旧历史日志漏框架事件/skipped run 日志问题已解决；history API 返回 `retries`，调度前置框架事件和 skip 事件都写入当前 retry。
- Confirmed (`2026-07-05_1823-check-history-chunking`): 修复定时停止/强停状态回归：终态 `LiveRun.request_stop()` / `request_force_stop()` 幂等，不会把已结束 run 改回 `stopping`；`SchedulerService.stop_current()` / `force_stop_current()` 对终态 current run 返回原状态；缓冲等待阶段产生的 log-only retry 会在 run finish 前 seal 并写入 retry history。`LiveRun.run_dict()` 不再让 metadata 覆盖核心字段，避免 `retry_count=max_retries` 误报。

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
- Confirmed (`2026-06-29_2137-project-state-docs`): 架构或工作流变更时应同步更新 `README.md`、`docs/README.md`、`docs/maa-runtime.md`、`docs/architecture-direction.md`、`.codex/project-history.md`、`.codex/project-lessons.md`。

---

## Latest Verification

- Confirmed (`2026-07-05_1926-inspect-concurrency`): 新增全局 ADB 设备运行仲裁后，`uvx ruff check src tests`、`uv run python -m compileall -q src tests`、`uv run pytest -q`（57 passed）、`git diff --check` 均通过；`linux-maa-webui.service` 已重启且 `/api/settings` 本机检查通过。
- Confirmed (`2026-07-05_1823-check-history-chunking`): `uv run pytest -q tests/test_maa_logs.py tests/test_backend_utilities.py`（31 passed）、`uv run python -m compileall -q src tests`、`uv run pytest -q`（51 passed）、`uvx ruff check src tests`、真实 `f7ecfac6dafc.stderr.log` 管线回放、`cd frontend && npx tsc --noEmit --noUnusedLocals --noUnusedParameters --pretty false`、`git diff --check`、`cd frontend && npm run build` 均通过。Vite 仍有既有 500 kB chunk warning。
- Confirmed (`2026-07-04_1305-unify-run-log-sse`): 最新确认 `uvx ruff check src tests`、`uv run python -m compileall -q src tests`、`uv run pytest -q`（48 tests）、`cd frontend && npx tsc --noEmit --noUnusedLocals --noUnusedParameters --pretty false`、`cd frontend && npm run build`、`git diff --check` 均通过。Vite 仍有既有 500 kB chunk warning。`linux-maa-webui.service` 已重启并在 2026-07-05 02:38 UTC 后健康检查通过。
- Confirmed (`2026-07-04_1115-review-cleanup`): `uvx ruff check src tests`、`uvx vulture src tests --min-confidence 80`、`uv run python -m compileall -q src tests`、`npx tsc --noEmit --noUnusedLocals --noUnusedParameters --pretty false`、`uv run pytest -q`（50 tests）、`cd frontend && npm run build`、`uv run python -m linux_maa.tools.game --help` 均通过。Knip 仅误报 `@tailwindcss/vite` 未使用；该依赖由 `frontend/vite.config.ts` 使用，已保留。
- Confirmed (`2026-07-04_1047-audit-log-pipeline-audit`): 精简日志测试后，`uv run pytest -q` — 50 tests pass；`uv run python -m compileall -q src tests` pass；`cd frontend && npm run build` pass（仅既有 Vite chunk warning）✅
- Confirmed (`2026-07-04_1047-audit-log-pipeline-audit`): `uv run pytest -q` — 55 tests pass ✅
- Confirmed (`2026-07-04_1047-audit-log-pipeline-audit`): `uv run python -m compileall -q src tests` ✅
- Confirmed (`2026-07-04_1003-audit-log-pipeline`): `uv run pytest -q` — 54 tests pass ✅
- Confirmed (`2026-07-04_1003-audit-log-pipeline`): `uv run python -m compileall -q src tests` ✅
- Confirmed (`2026-07-04_1003-audit-log-pipeline`): `cd frontend && npm run build` — pass (existing Vite chunk warning only) ✅
- Confirmed (`2026-07-04_0341-log-template-framework`): `uv run pytest -q` — 51 tests pass ✅
- Confirmed (`2026-07-04_0341-log-template-framework`): `uv run python -m compileall -q src tests` ✅
- Confirmed (`2026-07-04_0341-log-template-framework`): `cd frontend && npm run build` — pass (existing Vite chunk warning only) ✅
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): `uv run python -m compileall -q src tests` ✅
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): `uv run pytest -q` — 45 tests pass ✅
- Confirmed (`2026-07-03_1200-audit-and-refactor-codex`): `cd frontend && npm run build` — pass (existing Vite chunk warning only) ✅
- Confirmed (`2026-07-03_0105-audit-log-module`): `systemd-analyze verify` pass, `systemctl is-enabled` returns `disabled`, port 8000 free ✅
