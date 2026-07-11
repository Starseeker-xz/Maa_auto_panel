# Maa Auto Panel 项目说明（面向 Agent）

本文给第一次接触仓库的 agent 提供高密度上下文。开始修改前仍须阅读根目录 `AGENTS.md`，并按其中要求加载 `.codex/` 状态；本文不是执行规则的替代品。

## 1. 项目是什么

Maa Auto Panel 是一个面向单用户、可信内网环境的自动化控制面板。它目前以明日方舟自动化工具 MAA（`maa-cli` + MaaCore）为首个 integration，通过浏览器提供任务配置、手动执行、定时执行、维护更新、游戏 APK 更新、实时日志、停止/强停和历史查看。

它不是 MaaCore 的重实现。面板负责配置管理、调度、进程生命周期、并发仲裁、状态与可观测性；实际游戏自动化仍由外部 `maa-cli`/MaaCore 完成。目标 Android 环境当前是 LAN 上通过 TCP ADB 连接的 redroid。

## 2. 产品目标与边界

近期目标是把已经可用的 MAA 面板整理成清晰、长期运行可靠、可扩展到其他命令行自动化工具的通用框架。MAA 应逐渐成为一个 integration，而不是渗透所有通用模块的核心概念。

明确边界：

- 单用户、可信 LAN；目前不引入账号、token、RBAC、用户数据库或认证反代。
- 单进程、单实例；scheduler、JSON store 和资源协调器都没有跨进程一致性，禁止裸机与容器实例同时操作同一设备和数据。
- 目前不需要数据库、微服务或动态第三方插件加载器。
- 自定义扩展优先采用仓库内可信 manifest、Action/Integration registry 和明确的脚本接口。
- 项目尚未正式发布，架构调整直接形成最终布局，不保留旧 API/旧目录兼容层。

## 3. 技术栈

- 后端：Python 3.12、FastAPI、Uvicorn，包与命令行入口均由 `pyproject.toml` 管理，依赖使用 uv 锁定。
- 前端：React、TypeScript、Vite；组件基础来自 Radix/shadcn 风格组件，配置表单使用 JSON Forms。
- 持久化：可读 JSON、JSONL、TOML 和领域配置文件；当前没有数据库。
- 实时通信：Server-Sent Events（SSE）传输当前运行状态的增量 patch。
- 外部执行：`maa-cli`、ADB、维护命令、工具和脚本均作为受管子进程运行。
- 部署：当前开发常驻方式是 systemd；Dockerfile/Compose 已用于定义未来容器边界，目标为非 root、普通 bridge 网络、外部 TCP redroid。

## 4. 顶层目录与数据所有权

```text
src/maa_auto_panel/      Python 后端
frontend/                React 前端
tests/                   后端测试
docs/                    架构、MAA 集成与上游 schema 资料
data/                    框架拥有的 config/state/history/debug
runtime/                 框架无关的 integration 安装与自身运行状态
  maa/                   maa-cli、MaaCore、resource、XDG data/cache/state
cache/downloads/         可删除、可重建的 APK/patch 下载缓存
```

四个根边界分别由路径模型表达：

- `ApplicationPaths`：随应用发布的只读前端和 schema。
- `FrameworkPaths`：框架拥有的配置、状态、历史和诊断。
- `MaaInstallation`：MAA integration 的 binary、resource 和 XDG 目录；默认位于 `runtime/maa`。
- `CachePaths`：可重建下载缓存。

MAA 的可编辑配置仍由面板管理，因此位于 `data/config/maa`，不随 runtime 重装删除。环境变量分别是 `MAA_AUTO_PANEL_DATA_DIR`、`MAA_AUTO_PANEL_RUNTIME_DIR` 和 `MAA_AUTO_PANEL_CACHE_DIR`。

## 5. 后端模块地图

- `web/`：FastAPI app、lifespan、SSE 和 HTTP routes；`web/services.py` 组装服务对象。
- `config/`：应用设置、maa-cli task/profile 配置、schema 验证及 framework metadata 预处理。
- `scheduler/`：schedule 配置、游戏日时间语义、触发状态、每日统计和重试策略。
- `run_manager/`：通用运行内核，包含 command 执行、状态模型、history store、route 和 coordinator。
- `maa/`：MAA 专属 runner、维护更新、结果采集、关卡与基建解析、日志模板。
- `logs/`：通用可见日志流水线，负责 source、block、裁剪和 retry 内日志结构。
- `notifications/`：五类全局通知的 tag registry、独立设置、事件 broker 与外部发送接口。
- `diagnostics.py`：原始 stdout/stderr、框架日志和诊断文件；与用户可见 history 分离。
- `process.py`：受管流式子进程与停止/超时行为。
- `tools/`：非 MAA 主任务工具；目前包含游戏 APK 更新。
- `paths.py`：应用、框架数据、integration runtime、cache 的路径所有权模型。

## 6. 骨干运行逻辑

一次运行的大致链路为：

```text
HTTP / scheduler trigger
  -> 对应领域 service/driver 生成 RunStartPlan
  -> GenericRunManager 建立 LiveRun/LiveRetry
  -> RunCoordinator 仲裁 ADB 等资源
  -> manager 根据 callbacks 构造命令并调用流式进程执行器
  -> raw output 同时进入 Diagnostics 与结构化 RunLogBuffer
  -> 领域 collector 解析 MAA 子任务结果
  -> callbacks 返回 RetryDecision
  -> manager 负责 retry、终态、持久化和状态通知
  -> SSE 将增量 patch 推送给前端
```

核心职责约束：通用 manager 拥有 command、retry loop 和 lifecycle；MAA/scheduler 等领域 callbacks 只决定动态命令、原始行消费、attempt 结果与是否继续。不要把 retry loop 再移回领域 driver。

当前有四类受管运行：手动 MAA、定时任务、工具、维护。它们共享 `RunCoordinator`，优先级大致为 schedule auto > schedule manual > normal，并主要按 ADB address 仲裁冲突。

## 7. 配置与调度

MAA task 配置位于 `data/config/maa/tasks`。task item 可以带 `[tasks.framework]` metadata；它不是 maa-cli schema 的一部分。执行前，框架会解析 managed params、关卡或基建动态选项，移除 framework metadata，并在 `runtime/maa/generated-configs` 生成 maa-cli 可接受的临时配置。

schedule 位于 `data/config/framework/schedules`。scheduler 负责触发时刻、游戏日、每日成功/运行计数、task enable 集合和 retry policy。手动运行不套用 schedule 的每日策略，但复用相同的 MAA 执行与“成功任务后续 retry 跳过”能力。

## 8. 状态、历史、诊断与实时 UI

这四类信息必须保持分离：

- live state：内存中的当前 run/retry，供当前状态 API 与 SSE 使用。
- state：`data/state/framework` 下的近期索引、scheduler bookkeeping 等可恢复状态。
- history：`data/history/framework/runs` 下按 run/retry 保存的用户可见结构化历史。
- diagnostics：`data/debug/framework` 下的框架日志、事件 JSONL 和外部进程原始输出。

SSE 不是固定频率全量轮询。服务在状态变化时通知 stream，stream 推送 run 字段和 retry list delta；空闲时只发送 keep-alive。

全局通知使用独立 `/api/notifications/events` SSE，不依附任何页面的运行流。runtime 缺失在服务启动时检查；版本更新在 maintenance update-info 检查得到结果时发布；手动 MAA、自动 schedule、手动触发 schedule 在通用 manager 完成持久化后发布，用户停止不通知。五类 tag 的 Toast/未来 external 策略保存在 `data/config/framework/notifications.toml`。

## 9. 进程与停机

所有外部命令使用独立 POSIX process group。普通停止向完整进程组发送 SIGTERM，强停发送 SIGKILL。FastAPI lifespan 拥有 scheduler 和 WebServices 生命周期；SIGTERM 时先关闭 SSE、停止新调度和新运行，再给所有 manager 共享的 60 秒正常停止 deadline，之后共享 15 秒强停/持久化 deadline，最后 flush diagnostics 并 join 线程。

不要把 daemon thread、逐 manager 累加 timeout 或只杀父进程当作停机方案。

## 10. 当前重要风险与下一步

- `process.py` 的 text `readline()` 路径可能被“可读但没有换行”的输出阻塞，应改为 non-blocking byte read + incremental decode。
- maintenance 更新 runtime 尚未取得 exclusive `runtime:maa` resource claim，可能与正在运行的 MAA 并发覆盖文件。
- coordinator 同优先级冲突会无限等待，HTTP start 可能占住 worker；应改为明确 409 或显式队列。
- manager 内存引用和 history JSON retention 尚未完整清理，长期运行可能增长。
- active retry 只在 seal 时持久化，崩溃可能丢失当前 retry 的结构化可见日志。
- 游戏 APK 下载缺少 hash、package identity 和签名证书的完整校验。
- 上游 Linux MAA artifact 当前观察到 OpenCV SONAME `.411/.412` 混合；`maa version` 成功不代表 ADB plugin 可加载，真实设备 smoke 仍需自洽 runtime。

当前路线优先级：运行与安全基线 → 缩窄通用模块对 `MaaRuntime` 的依赖 → 内部 Action/Integration registry → 用第二个 integration 验证抽象。一次只聚焦一个相关模块或边界。

## 11. 修改与验证提示

- 修改前先读目标模块及相似实现，确认问题是否属于更健康的边界调整。
- 保留工作区既有未提交改动；不要按旧 HEAD 推断当前架构。
- 项目命令优先使用 `.venv/bin/python -m pytest` 或 `uv run`；本机可能没有 Ruff executable。
- 前端至少执行 `npm run build`；后端改动按风险执行相关测试或完整 pytest，并运行 `git diff --check`。
- 未经用户明确要求，不执行 Docker build/up；容器测试也不得与 systemd 实例并行连接同一 redroid。
- 架构和路径变化后同步检查 `README.md`、`docs/README.md`、`docs/maa-runtime.md`、`docs/architecture-direction.md`、审计文档及 `.codex/project-history.md`。
