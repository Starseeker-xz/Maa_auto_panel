# Project Lessons

仅记录未来仍容易复发的项目级陷阱。每项带来源会话。

## Runtime and process control

- `2026-07-10_2207-graceful-shutdown`: Uvicorn 0.49 的 graceful timeout 会取消未退出 SSE 并记录 traceback；只设置 timeout 不算干净关闭。SIGTERM 到达时先广播应用 shutdown token，SSE 用短轮询主动结束，timeout 仅作兜底。
- `2026-07-10_2207-graceful-shutdown`: Uvicorn 0.49 清理后会重新 raise 捕获的 SIGTERM；经 `uv run` 会成为 status 143，并让 systemd 记录 failed。容器入口需要 shutdown-aware Server：保留信号捕获和清理，但成功后不重新 raise SIGTERM。
- `2026-07-10_2207-graceful-shutdown`: 容器关闭预算必须使用共享 absolute deadline；先同时通知所有 manager，再按同一 deadline join，不能给每个 manager 顺序分配完整 timeout。
- `2026-07-10_0416-full-project-audit`: pipe 可读不代表 `TextIOWrapper.readline()` 不阻塞。流式进程必须 non-blocking 读 bytes、自行增量解码/分行，并测试无换行 partial output 下的 timeout/stop/force-stop。
- `2026-07-10_0416-full-project-audit`: runtime 更新动作必须与使用该 runtime 的 run 互斥；需要 shared/exclusive resource claim，不能只锁 ADB device。
- `2026-07-10_0416-full-project-audit`: daemon thread 不是 shutdown 方案。FastAPI lifespan/CLI signal 必须停止 scheduler、收尾 active run、杀 process group、持久化后 join。
- `2026-07-06_0037-callback-run-manager`: 通用 manager 拥有 lifecycle/command/retry loop；领域 callbacks 只提供差异和 `RetryDecision`。不要恢复 driver-owned retry loop。
- `2026-07-05_1823-check-history-chunking`: retry seal 后再写 event 会产生额外 log-only retry；retry-next/limit 等事件必须在 seal 前写入。stop/force-stop 对终态必须幂等。
- `2026-07-04_1003-audit-log-pipeline`: 不要在持有非重入锁时调用会再次通知状态的 helper；scheduler 曾因此死锁。保持相关路径可重入或把 callback 移到锁外。

## State and diagnostics

- `2026-07-04_1047-audit-log-pipeline-audit`: 不要用有界日志列表长度当持久 cursor；裁剪后会错位。retry/history 使用独立持久结构或单调序号。
- `2026-07-01_2153-manage-service-history`: 保持状态、结构化 history、外部诊断日志和 Python framework logging 分离；不要重新合成一个大而含糊的 history/log service。
- `2026-07-10_0416-full-project-audit`: recent index retention 不等于 history retention。淘汰 index 时必须同步处理 history/artifacts；完成 run 后释放 manager plan/callback 引用。
- `2026-07-10_0416-full-project-audit`: JSON parse failure不能静默当空状态后继续覆盖。隔离 corrupt 文件、记录诊断并阻止破坏性写入。

## Configuration and frontend

- `2026-07-11_1805-consolidate-audits`: 实现前端交互前先检查现有 shadcn/Radix/Sonner 通用组件；缺失时优先按项目 `components.json` 引入官方组件到 `components/ui`，不要手搓 Toast 生命周期、动画、Dialog/Drawer/Tabs 等基础设施。业务组件应主要组合通用 primitives，只保留领域状态与薄样式封装。
- `2026-07-10_1752-audit-data-paths`: 项目尚未发布时不设计旧布局、旧 API 或旧数据的前向/向后兼容，不添加 migration CLI、layout version、兼容读取或过渡 facade。直接修改为最终结构，并对本机开发数据做一次性调整；只有用户明确提出发布兼容需求后才增加兼容层。
- `2026-07-10_0004-complete-rename-maa-auto-panel`: 重命名不能无上下文全局替换 `maa_auto_panel`；包名、metadata namespace、placeholder、schema key、运行目录必须分别核对。
- `2026-07-04_1115-review-cleanup`: 删除 re-export 时搜索所有 helper/包级间接导入，并把调用方改到真实定义模块。
- `2026-07-02_1933-config-sync-ui-schema`: 删除 task editor schema 字段时同步模板 general/advanced keys，避免悬挂 JSON Forms 控件。
- `2026-06-30_1743-fix-infrast-plan-select`: 同一 UI 事件同时修改 params 与 framework managed metadata 时使用一次合并 patch，避免双更新覆盖。
- `2026-07-01_1506-sse-log-delta`: Playwright 不要等待含 EventSource 页面的 `networkidle`；使用 `domcontentloaded` + 目标 DOM 断言。

## Environment

- `2026-07-11_1805-consolidate-audits`: 不要直接执行 `runtime/maa/bin/maa version` 判断面板 runtime；缺少 `MAA_CONFIG_DIR` 与 XDG_DATA/CACHE/STATE 环境时会误报无法读取 MaaCore。使用 `scripts/maa-env maa version` 或 `MaaRuntime.env()` 等价环境。本次直接执行曾误判更新后 Core 损坏，正确环境确认 MaaCore v6.14.1 且用户 smoke 任务可运行。
- `2026-07-10_0416-full-project-audit`: 仓库移动/重命名后，venv console script shebang 和 editable install 元数据可能仍指向旧路径。优先重建/重装 `.venv`；临时验证用 `.venv/bin/python -m pytest`，不要仅信 `which pytest`。
- `2026-07-10_0416-full-project-audit`: Docker multi-stage 复制 venv 时 builder/runtime 必须保持相同绝对路径，或使用 wheel 安装；否则 console-script shebang 会指向 builder 路径。`tini` 与 Compose `init: true` 二选一。
- `2026-07-10_0416-full-project-audit`: 当前 scheduler/coordinator/store 仅支持单进程；容器化时禁止副本扩容、滚动双实例和 systemd/Compose 同时运行，否则会重复触发 schedule 且资源锁不跨进程。
- `2026-07-10_2207-graceful-shutdown`: 当前 Starlette `TestClient` 要求未安装的 `httpx2`。生命周期测试直接使用 `app.router.lifespan_context(app)`；不要仅为该测试引入新 HTTP client 依赖。
- `2026-06-30_2056-scheduled-execution`: 仓库搜索排除 `frontend/node_modules`、`docs/maa-upstream`、`runtime`、`external` 和运行日志目录；系统级一次性脚本使用 `python3`，项目命令使用项目解释器。
