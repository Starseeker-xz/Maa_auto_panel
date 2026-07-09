# Run Manager Callback-First 重构计划

当前日期：2026-07-06

本文是当前运行管理重构的准确信息源。旧的 driver-owned-loop 方案已取消。

## 1. 目标

统一手动运行、定时运行、工具运行、维护运行的 live-run 生命周期：

- `GenericRunManager` 接收初始命令、重试次数、超时、日志模板、资源、优先级和可选 callbacks。
- manager 内置运行、重试、停止、强制停止、日志管线、SSE 状态更新、retry 持久化、run 持久化和脚本 hook。
- 外部逻辑只通过 callbacks 做领域决策和必要副作用，不再自己写 retry while loop。
- 没有领域差异的运行只传 `CommandSpec`；工具和维护应走这个默认模式。
- 手动 MAA 和定时 MAA 只把 task 选择、配置生成、raw line 解析、重试决策、daily stats 等领域逻辑放进 callbacks。
- 外部脚本是 manager 默认能力，可在 `before_run`、`after_run`、`before_retry`、`after_retry` 触发，输出进入同一可见日志管线并使用特有 source 标签。

## 2. 非目标

- 不让通用 manager 理解 MAA task、schedule policy、profile、ADB 语义。
- 不保留 `RunDriver`、`RunContext`、`CommandRunDriver` 兼容层。
- 不改变前端 `{run, retries}` 外层状态形状；run/retry 内部字段已破坏性收敛为基础字段 + `metadata` + `artifacts`。
- 不把 schedule CRUD、后台 loop、timeline、daily stats 查询放进通用 manager。
- 本轮不强制改造启动 API；启动前置逻辑仍留在各领域 service。

## 3. 模块结构

```text
src/linux_maa/run_manager/
  __init__.py
  state.py        # RunTimeouts, LiveRun, LiveRetry, now_text
  store.py        # RunStateStore 和历史持久化
  coordinator.py  # RunCoordinator, RunLease, RunConflictError
  command.py      # CommandSpec，仅描述命令/env/output_log_file
  logs.py         # RunLogProfile 与通用 stream 日志 profile
  manager.py      # GenericRunManager、RunStartPlan、callbacks、script hooks
  router.py       # 通用 current/status/log/stop/SSE 控制路由

src/linux_maa/run_resources.py
```

`command.py` 不再包含 driver；`CommandSpec` 是 manager 内置命令模式的输入。

## 4. GenericRunManager 职责

`GenericRunManager.start(RunStartPlan)` 做：

- 创建 `LiveRun` 和第一个 `LiveRetry`。
- 通过 `RunCoordinator` 申请资源。
- 按 `max_retries` 内置循环执行命令。
- 每轮运行前后触发 callbacks 和 script hooks。
- 调用 `run_streaming_process()`，处理 stop、force-stop、timeout、stdout/stderr、raw line。
- 使用 `RunLogProfile` 写可见日志和诊断文件。
- 持久化 retry 和最终 run。
- 对外提供 `current()`、`get()`、`current_response()`、`wait_for_change()`、`stop()`、`force_stop()`。

停止行为：

- stop 请求会把 run 标为 `stopping`，并让当前进程 graceful terminate。
- 如果当前 attempt 因 stop 结束，manager 会强制清除 `continue_retry`。
- 若 stop 已经请求，manager 不再执行 `before_retry`、`before_retry` 脚本、retry-start 文案或通用 retry-next 文案。
- 这用于修复“用户中断后仍残留第 N 次重试/准备重试”的现象。

## 5. RunStartPlan

核心字段：

- `kind`, `title`
- `command: CommandSpec | None`
- `max_retries`
- `callbacks: RunCallbacks`
- `timeouts: RunTimeouts`
- `log_profile: RunLogProfile`
- `script_hooks: RunScriptHooks`
- `script_log_profile: RunLogProfile`
- `metadata`, `artifacts`, `log_files`, `event_log_file`
- `initial_attempt_payload`
- `history_scope`
- `resources`, `priority_name`, `priority`, `force_after_seconds`
- `text: RunTextTemplates`

`RunTextTemplates` 只承载通用 lifecycle 文案，例如 start、retry-start、exit-code、stop、force-stop、timeout 里的进程名等。领域动态文案放 callback 里追加 event。

## 6. Callback 模型

所有 callback 都可选：

- `on_start(attempt) -> RetryDecision | None`
  - 第一个 retry 创建后触发。
  - 可用于写启动日志、检测无任务并直接返回 skipped。
- `before_retry(attempt, previous_decision) -> None`
  - 第二轮及以后、真正准备下一轮命令前触发。
  - 可用于 retry buffer wait、修改外部状态。
- `before_attempt(attempt) -> None`
  - 每轮命令构建前触发。
- `build_command(attempt) -> CommandSpec | None`
  - 可动态生成本轮命令；未提供时使用 `RunStartPlan.command` 或上轮 `RetryDecision.next_command`。
- `on_raw_line(attempt, stream, line) -> None`
  - 透传原始 stdout/stderr 行。MAA 使用它喂给 `MaaTaskResultCollector`。
- `evaluate_attempt(attempt, result) -> RetryDecision | None`
  - 根据进程结果和领域状态决定本轮 retry 状态、run 最终状态、是否继续 retry、下一轮 command/payload。
- `after_attempt(attempt, result, decision) -> RetryDecision | None`
  - manager 写完默认 exit-code/completed 事件后触发。
  - 可追加动态“准备重试: xxx”或“重试次数已达上限”文案。
- `on_finish(api, completion) -> RunCompletion | None`
  - run 结束持久化前最后修正 summary/status。

`RunAttempt` 是只读 attempt 视图，暴露：

- `run_id`, `retry_id`, `retry_index`, `attempt_index`, `max_retries`
- `payload`, `previous_decision`, `metadata`
- `stop_requested`, `force_stop_requested`
- `add_event()`, `wait_for_stop()`, `configure_log()`, `mark_updated()`

领域数据通过 `RetryDecision.next_attempt_payload`、`RetryDecision.retry_metadata`、`RetryDecision.retry_artifacts`、`RunCompletion.metadata_patch`、`RunCompletion.artifacts` 回传；通用 manager 不再有 `task_ids`、`task_results`、`generated_config_dir`、`maacore_log_file` 等字段。

它不是旧 `RunContext`，不允许外部 begin/finish retry 或 finish run；生命周期仍由 manager 控制。

## 7. Script Hooks

`RunScriptHooks` 支持：

- `before_run`
- `after_run`
- `before_retry`
- `after_retry`

每个 hook 是 `RunScriptSpec`：

- `command: CommandSpec | Callable[[RunAttempt], CommandSpec | None]`
- `label`
- `source_prefix`
- `timeouts`
- `log_profile`

脚本 stdout/stderr 会使用 source：

```text
{source_prefix}:{hook}:stdout
{source_prefix}:{hook}:stderr
```

例如定时重启脚本使用：

```text
script:before_run:stdout
script:before_run:stderr
script:before_retry:stdout
script:before_retry:stderr
```

诊断文件由 `script_log_profile.diagnostic_sink` 写入。

## 8. 各运行类型匹配方式

### 工具运行

- 启动前完成 tool config sanitize 和 command build。
- `RunStartPlan.command = CommandSpec(...)`
- 不需要 callbacks。
- 使用 tool log profile 和 tool diagnostics。
- ADB 资源由调用方通过 `resources` 传入。

### 维护运行

- 启动前把 maintenance kind 映射为 maa-cli command。
- `RunStartPlan.command = CommandSpec(...)`
- 不需要 callbacks。
- `max_retries=1`。
- update-info 检查继续留在 maintenance manager，不进入 run manager。

### 手动 MAA

启动前：

- 读取 profile，计算 ADB resources。
- 读取 task config。
- 解析 task policies 和 enabled task ids。

callbacks：

- `on_start`：无 enabled task 时写日志并返回 skipped。
- `build_command`：每轮根据 `attempt.payload["task_ids"]` 生成临时 maa-cli task config 和命令。
- `on_raw_line`：把 `maa-cli:stderr` 喂给 `MaaTaskResultCollector`。
- `evaluate_attempt`：结合 return code、task result、stop/timeout 判断 retry status；计算下一轮未完成 task；捕获 MaaCore log delta；通过 `next_attempt_payload`、`retry_metadata`、`retry_artifacts` 返回领域数据。
- `after_attempt`：非 stopped 时追加动态重试提示。

### 定时 MAA

启动前：

- schedule due/manual trigger 判断。
- game day/timezone。
- initial task selection。
- priority/resource。

callbacks：

- `on_start`：写本次实际任务和跳过原因；无任务时返回 skipped。
- `before_retry`：按 schedule retry buffer 等待，等待期间尊重 stop。
- `build_command`：每轮生成 schedule 专用临时 config/profile 和 maa-cli command。
- `on_raw_line`：同手动 MAA。
- `evaluate_attempt`：通过 `SchedulerStateStore` 更新 daily stats，按 retry policy 计算下一轮 task；计算最终 `succeeded`/`soft_failed`/`failed`/`stopped`。
- `after_attempt`：非 stopped 时追加动态重试提示。

重启脚本：

- `restart.mode == "before_run"` 映射到 `RunScriptHooks.before_run`。
- `restart.mode == "before_retry"` 映射到 `RunScriptHooks.before_retry`。

## 8.5. Store 边界

- `RunStateStore` 只保存通用 run/retry/history；`StoredRun` 输出基础字段、`metadata`、`artifacts`、`history_scope`。
- history 路径由领域层传入 `history_scope`，例如 `("manual",)`、`("schedules", schedule_id)`、`("tools", tool_id)`、`("maintenance", kind)`。
- scheduler daily stats 和 trigger 去重已迁出到 `scheduler/state.py` 的 `SchedulerStateStore`。

## 9. Web SSE 与路由

通用 router 已承担：

- current/status 获取
- run log 获取
- stop / force-stop
- SSE 订阅

启动 API 仍保留在各领域 router，因为启动前置输入和校验差异较大。

## 10. 当前验证要求

实现后至少运行：

```bash
uvx ruff check src tests
uv run python -m compileall -q src tests
uv run pytest -q
git diff --check
```

已新增/保留的重点测试：

- manager 内置 command 运行、重试、停止、timeout。
- stop 后不会创建下一轮 retry，也不会追加“第 2 次重试/准备重试”。
- 通用 manager payload 驱动下一轮 retry，且 public retry 不含 task/MAA 顶层字段。
- 手动 MAA 无 enabled task 时 skipped retry 持久化，task 结果进入 retry metadata，生成配置/MaaCore 日志进入 artifacts。
- 定时 MAA 无 selected task 时 skipped retry 持久化，scheduler daily stats/trigger 由 `SchedulerStateStore` 覆盖。
- script hook 输出进入可见日志和 diagnostics。
