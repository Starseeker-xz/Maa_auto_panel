# Project Lessons

Mistake notebook for recurring project-specific issues. Source session id on each entry.

---

## Testing

- `2026-06-26_1727-webui-config-runner`: FastAPI `TestClient` 可能需要额外安装 `httpx2`。当前验证用真实 uvicorn + curl，或显式添加测试依赖。
- `2026-06-30_0124-config-save-delete`: 用 FastAPI 测试临时仓库时使用 `create_app(explicit_repo_root)`（修复后）；修复前 `create_app(repo_root)` 内部仍调 `find_repo_root(repo_root)` 可能爬到真实仓库。
- `2026-06-30_1934-scheduled-retry-architecture`: 仓库测试需要 uv dev 依赖组；`pytest` 应在 `[dependency-groups].dev` 中。运行用 `uv run pytest`。

## Frontend

- `2026-06-29_1929-shadcn-sidebar`: 本地 shadcn/Radix 封装中，不要在注入多个兄弟子元素的组件中使用 `Slot`/`asChild`。Radix `Slot` 期望单个有效子元素，否则运行时空白页。侧边栏导航用真实单子 `Link` 或 `useNavigate()`。
- `2026-06-30_0014-task-editor-fixes`: 拆分前端 JSON 编辑器模板时，更新模板聚合/导入代码并验证所有 schema enum 表单仍路由到自定义渲染器。`oneOf`/`const` 选项需要 `isOneOfEnumControl`，否则 select 渲染器可能不生效。
- `2026-06-30_0124-config-save-delete`: 主任务编辑器页面，以 URL 中的任务配置为单一真相来源。单独的 `taskConfig` state + `initialTaskConfig` ref 会导致路由变更被覆盖回初始配置。
- `2026-06-30_0124-config-save-delete`: 浏览器前端检查可用 Playwright + Chromium（`/root/.cache/ms-playwright/`），用于视觉/布局验证。
- `2026-06-30_1743-fix-infrast-plan-select`: JSON Forms 控件同时管理 `params` 和 `linux_maa.managed_params` 时，避免在同一 UI 事件中分开触发父级更新。用一个合并回调/patch。
- `2026-07-01_1506-sse-log-delta`: 浏览器测试含 SSE/EventSource 连接的页面时，不要等 Playwright `networkidle`；长连接事件流使页面永不 idle 并超时。用 `domcontentloaded` + 目标 DOM 断言或短固定等待。
- `2026-07-02_1933-config-sync-ui-schema`: 删除任务编辑器 schema 字段时，同步从模板 `general`/`advanced` 列表中移除 key，避免产生悬挂的 JSON Forms 控件。

## Backend

- `2026-06-30_1743-fix-infrast-plan-select`: `MaaRuntime` 没有 `discover()` 辅助方法。直接构造 `MaaRuntime(find_repo_root())`。
- `2026-06-30_2056-scheduled-execution`: 仓库级 `rg` 搜索应排除 `frontend/node_modules`、`docs/maa-upstream`、`runtime`，或显式指定目标路径。
- `2026-06-30_2056-scheduled-execution`: 本环境无裸 `python` 命令。仓库内用 `uv run python ...` 使用项目解释器和依赖。
- `2026-06-30_2342-full-project-audit`: 不要把原始 scratch 产物或上游源码检出放在 tracked `.codex/conversations/**/scratch/` 中。未来会话应保持 scratch untracked，耐久发现汇入 project history/session 文件。
- `2026-07-01_1312-explain-log-flow`: 拆分领域实现为多个文件时，保持在领域子包内而非散落为父包的兄弟模块。如 WebUI 日志内部应属于 `logs/` 顶级子包。
- `2026-07-01_1506-sse-log-delta`: 代码修改前先做目标模块聚焦审计。如有明显架构风险，主动提出并处理低中风险改进，而非仅做最窄补丁。
- `2026-07-01_2153-manage-service-history`: 不要手动搜索进程名或信任 `runtime/linux-maa/webui.pid`（该文件来自旧分离启动）。用 systemd unit `linux-maa-webui.service` 管理生命周期。
- `2026-07-01_2153-manage-service-history`: 不要把高频原始进程输出倒入高级 JSONL 事件日志，不要用一个"history/log"类兼做状态和诊断。保持三分离：状态（`state/`）、诊断（`debug/`）、Python logging（框架日志）。
- `2026-07-02_2144-manual-stop-delay`: 如 maa-cli 启停卡在"已连接"，先查 MaaCore 日志是否有 `adb devices ret 0, cost 60001 ms`。本地 ADB server 缺失使 MaaCore 在 NativeIO 中等待 60 秒；`kill_adb_on_exit = true` 使每次复发。
- `2026-07-02_2245-tools-page`: 对实时进程日志，不要对生产者（如 `download_file()`）做专项进度条折叠。在 `run_streaming_process()` 中保留原始回车符，在 `RunLogTranslator` 中折叠终端重绘。
- `2026-07-02_2245-tools-page`: 启动项目 Python CLI 作为实时日志子进程时用 `sys.executable -u` 或 `PYTHONUNBUFFERED=1`。`stdout=PIPE` 时普通 `print()` 输出会被块缓冲，可能只在进程退出时才到达。
- `2026-07-03_0105-audit-log-module`: systemd 重启 WebUI 时浏览器持有的 SSE 连接可能触发 unit 停止超时和 SIGKILL。重启后验证 `systemctl status`、`ss -H -ltn sport = :8000`，或重试 curl。

## Architecture & Process

- `2026-06-29_2137-project-state-docs`: 修改代码、配置布局、运行时行为、依赖、CLI 命令、WebUI 路由或前端结构时，显式检查 `README.md`、`docs/`、`.codex/project-history.md`、`.codex/project-lessons.md` 是否需要更新。
- `2026-06-29_2137-project-state-docs`: 项目仍早期，不存在第三方调用方。对于重设计或升级，优先简化架构和删除废弃功能，而非保留旧行为作为 fallback。只在有明确当前运维理由时保留 fallback。

## Environment

- `2026-07-03_1200-audit-and-refactor-codex`: 运行 `rg` 搜索时注意中文内容编码；用 `-e PATTERN` 传递以 `-` 开头的模式。
