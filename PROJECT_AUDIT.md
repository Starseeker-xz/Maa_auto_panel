# 项目综合审计报告

Session: `2026-07-03_1200-audit-and-refactor-codex`

上一轮审计报告（`BACKEND_AUDIT.md`、`FRONTEND_AUDIT.md`，session `2026-06-30_2342-full-project-audit`）仍然有效。本轮在上一轮基础上更新差异，并补充优化建议。

## 当前代码现状

### 后端：`src/linux_maa/`（56 个 Python 文件，约 6,700 行）

| 包/模块 | 文件数 | 职责 |
|---------|:-----:|------|
| 顶层（cli, diagnostics, process, run_state, settings, state, utils） | 8 | CLI 入口、日志基础设施、子进程执行、运行状态持久化、常量、通用工具 |
| `android/` | 2 | ADB 设备封装 |
| `config/` | 4 | maa-cli 配置 CRUD、schema 验证、任务参数投影、应用设置 |
| `game/` | 2 | Bilibili APK 下载/安装 |
| `logs/` | 6 | 流式日志翻译器、解析规则、中文翻译字典、有界缓冲区 |
| `maa/` | 5 | maa-cli 运行时、任务编排、关卡/基建选项、维护动作 |
| `scheduler/` | 7 | 定时配置管理、策略引擎、脚本 hook、后台循环（service ~760 行） |
| `storage/` | 3 | 低级文件 I/O、回收站 |
| `tools/` | 2 | 可插拔工具执行器 |
| `web/` | 10 | FastAPI 应用工厂、SSE 引擎、8 个路由模块 |

### 前端：`frontend/src/`（41 个 TS/TSX 文件，约 5,500–6,000 行）

| 层级 | 文件数 | 职责 |
|------|:-----:|------|
| `pages/` | 11 | MainPage (~430)、SchedulePage (~450)、SettingsPage (~700)、ToolsPage (~170) + 子面板 |
| `components/` | 15 | 公共组件（FormFields、DirtyActions、ProfileEditor、PrimitiveArrayEditor）+ 8 个 shadcn/ui 组件 |
| `lib/` | 12 | API 客户端、类型定义、JSON Forms 渲染器、SSE 流、工具函数、主题、轮询 hook |
| `config/` | 8 | 任务项默认值 + 7 个任务类型 JSON Forms 模式 |

### 配置文件与数据

| 目录 | 内容 |
|------|------|
| `config/linux-maa/` | `settings.toml` + 1 个定时配置 + 空 `scripts/` |
| `config/maa/` | `cli.toml` + 1 个 profile + 4 个任务 + 1 个排班 JSON + 1 个回收站条目 |
| `state/linux-maa/` | 4 个 JSON 状态文件（运行记录、尝试、统计、触发器） |
| `debug/linux-maa/` | `framework.log` + 18 个 JSONL 事件 + ~28 个外部日志 + 14 个 MaaCore 日志 |
| `runtime/maa/` | maa-cli 二进制 + MaaCore 资源 + 52 个运行日志 + 45 个生成配置 |
| `docs/` | 30+ 文档文件（含上游 MAA 中文文档镜像） |

### 测试：`tests/`（7 个文件，45 个测试）

| 文件 | 覆盖 |
|------|------|
| `test_maa_logs.py` | RunLogTranslator 任务生命周期解析 |
| `test_run_state_and_diagnostics.py` | RunStateStore + Diagnostics |
| `test_scheduler_policy.py` | 游戏日排序、重试策略 |
| `test_scheduler_service_status.py` | 最终状态判定 |
| `test_web_sse.py` | SSE 补丁生成 |
| `test_config_metadata.py` | 配置元数据 schema 验证 |
| `test_backend_utilities.py` | 路径安全、原子写、版本比较、流式输出 |

## 与上一轮审计的差异更新

### 已删除（`2026-07-03_1926-project-review`）
- ~~`src/linux_maa/adb.py`、`constants.py`、`game_update.py`、`maa_runner.py`~~ — 兼容 re-export 模块，零引用
- ~~`src/linux_maa/maa/logs/`~~ — 兼容导出目录，零引用
- ~~`MaaLogMessage`、`MaaSummaryLogRecord`、`MaaTaskLogRecord`、`MaaCliLogTranslator`~~ — 兼容别名
- ~~前端 `logs.ts` 中的 `translateLogLine()`~~ — 未使用

### 新增（`2026-07-xx` 各 session）
- `src/linux_maa/logs/` — 日志翻译从 `maa/logs.py` 提升为顶级包，含 translator、rules、translation、records、state
- `src/linux_maa/process.py` — 通用流式子进程原语（替代 `maa/process.py`），供 manual/scheduled/tool/maintenance 共用
- `src/linux_maa/run_state.py` — 持久化运行状态（替代 SQLite scheduler store）
- `src/linux_maa/scheduler/scripts.py` — 脚本 hook 管理
- `src/linux_maa/tools/` — 工具执行管理器
- `frontend/src/pages/ToolsPage.tsx` + `tools/` — 小工具页面（游戏更新等）
- `frontend/src/lib/runStream.ts` — SSE 流事件处理
- `frontend/src/pages/main/LogPane.tsx` — 重构：增量 SSE + 详情按钮

### 发现的新死代码
1. ~~**`src/linux_maa/scheduler/store.py`**~~ — `ScheduleStore = RunStateStore` 别名，全代码库零导入。**已删除**（`2026-07-03_1200`）。
2. ~~`src/linux_maa/logs/translator.py` 中的 `translate_maa_cli_log()`~~ — **经核实非死代码**：有测试覆盖（`test_compat_helper_flushes_one_shot_translation`），是一次性翻译公共 API 辅助函数。

### 前端重复常量
- `CONNECTION_TYPES`、`CONNECTION_CONFIGS`、`TOUCH_MODES` 在 `SettingsPage.tsx` 和 `ProfileEditor.tsx` 中重复定义。**已修复**（`2026-07-03_1200`）：提取到 `lib/constants.ts`。同时确认 `buttonVariants` 导入在两处均在 JSX 中使用，非死导入。

## 架构评估

### 优势
- **模块边界清晰**：基础设施 → 领域服务 → Web/API → 入口点，分层合理
- **无遗留标记**：代码库中无 TODO/FIXME/HACK 注释，状态干净
- **测试覆盖良好**：45 个测试覆盖核心路径（日志翻译、状态持久化、定时策略、SSE 补丁、版本比较）
- **零死导入**：所有 import 均解析到存在模块
- **配置与代码分离**：`config/`、`state/`、`debug/`、`runtime/` 目录职责明确

### 已知问题
1. **ADB 冷启动 60 秒延迟**（`2026-07-02_2144-manual-stop-delay`）：MaaCore 在无本地 ADB server 时 `adb devices` 耗时 60001ms，`kill_adb_on_exit = true` 导致每次运行后复发。建议预启动 ADB server + 考虑 `kill_adb_on_exit = false`
2. **GPU OCR 不可用**（`2026-06-30_2318-gpu-ocr-research`）：当前 MaaCore 仅编译 CPU ONNX Runtime provider，NVIDIA RTX 2080 Ti 无法使用
3. **`scheduler/service.py` 过大**（760 行）：仍是后端最大单文件，应拆分
4. **`SettingsPage.tsx` 过大**（700+ 行）：承载三组设置，应拆卡片

## 优化建议

### 高优先级（低风险、高收益）

1. ~~**删除 `scheduler/store.py`**~~ — **已完成**（`2026-07-03_1200`）
   - 风险：零（零导入）
   - 收益：消除死代码混淆

2. ~~**合并前端重复常量**~~ — **已完成**（`2026-07-03_1200`）
   - `CONNECTION_TYPES`、`CONNECTION_CONFIGS`、`TOUCH_MODES` 已提取到 `lib/constants.ts`

3. **拆分 `scheduler/service.py`**
   - 当前 760 行包含 loop、run lifecycle、attempt/retry、脚本 hook、日志、持久化
   - 建议拆出 `ScheduledRunExecutor`、`ScheduleDueChecker`、`AttemptRecorder`

4. **拆分 `SettingsPage.tsx`**
   - 当前 700+ 行，承载框架设置、设备 Profile、更新与资源三组
   - 建议拆为 `FrameworkSettingsCard`、`ProfileSettingsCard`、`MaintenanceSettingsCard`

### 中优先级（需一定投入）

5. **Service 方法返回 domain model 而非 API-shaped dict**
   - `MaaStageService`、`MaaInfrastService`、`MaintenanceActionManager` 直接返回 HTTP JSON 结构
   - 建议先定义 dataclass，再加 serializer 层

6. **统一 manual/scheduled/tool/maintenance 运行状态管理**
   - 四者共享 state、lock、process、output、done/status 模式
   - 建议抽轻量 `ProcessActionManager` 基类

7. **清理 `runtime/maa/run-logs/` 和 `generated-configs/`**
   - 52 个运行日志 + 45 个生成配置，可归档或添加自动清理策略

8. **修复前端未使用导入**
   - `TaskListPane.tsx` 和 `PrimitiveArrayEditor.tsx` 中的 `buttonVariants`

### 低优先级（可选）

9. **前端的 `JSON.stringify` dirty 比较**
   - `ConfigEditorPane`、`SchedulePage`、`SettingsPage` 使用 `JSON.stringify` 做深度相等
   - 当前键序可控，可接受；若引入自由 JSON 编辑需替换

10. **前端 bundle 体积优化**
    - Vite 500 kB chunk warning，来自 React/JSON Forms/Radix 集中打包
    - 可用 lazy routes 或 manualChunks 优化

11. **补充 FastAPI route 集成测试**
    - 当前无 TestClient 测试（历史上 httpx2 兼容问题）
    - 若依赖兼容，应补 404/400/409/422 行为测试

## 验证状态

- `uv run python -m compileall -q src tests` ✅
- `uv run pytest -q` — 45 个测试通过 ✅
- `cd frontend && npm run build` — 通过（仅有既有的 Vite chunk 警告）✅
- systemd unit `linux-maa-webui.service` 已注册、已验证、当前 inactive、disabled ✅
- 端口 8000 无监听进程 ✅
