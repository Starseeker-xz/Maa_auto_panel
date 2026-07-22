# 2026-07-14_2122-audit-scheduler

## 范围

- 只审计后端 scheduler 直接问题及其与通用 run manager 的必要交界；本阶段不修改产品代码。
- 用户要求先核实现状并详细说明问题与解决方案。

## 已确认事实

- `SchedulerService._loop()` 首次扫描前固定等待 15 秒；`_start_due_entries()` 只匹配扫描瞬间的 `%H:%M`，没有 scan cursor、due window 或 catch-up。
- trigger 去重键只有 `(schedule_id, entry_id, game_day)`，未记录 `scheduled_at`；同一 entry 在游戏日内改时间会与旧 occurrence 冲突，重复 entry id 也会碰撞，配置读取目前未验证 entry id 唯一性。
- 自动触发顺序为 `GenericRunManager.start()`（先创建 durable run）返回后，再写 scheduler trigger。两次写之间崩溃会留下已创建/recovered run、但无 trigger，catch-up 后可能重复启动。
- scheduler manager 自身已有 active run 时，`start()` 同步抛 `Conflict`，当前只在目标分钟内重试；跨 manager 的资源冲突则可能在线程中形成 failed run，并已被标 trigger，语义与日志中的 deferred 不一致。
- `ScheduledMaaRunCallbacks.evaluate_attempt()` 在 retry 写入 `RunStateStore` 前更新 daily stats；更新无 retry-id 幂等键。进程崩溃或 retry 持久化失败会产生 stats/history 分叉。
- `evaluate_attempt()` 用 attempt 完成时的当前 game day 更新 stats，而 initial selection 与 run metadata 使用启动时 game day；跨游戏日 reset 的长 run 会把选择与统计分属两天。
- `GenericRunManager._finish_retry()` 先 seal/publish live retry，再调用 `store.add_retry()`；持久化失败后 retry 已 closed，异常收尾不会重试 add_retry，甚至可能随后把 run 持久化为 terminal。这是 scheduler stats 一致性问题背后的通用 retry 提交缺陷。
- scheduler service 同时承担扫描/触发、MAA attempt adapter、CRUD/status facade；其中 MAA attempt 逻辑与 `maa/runner.py` 大段重复。
- 现有 scheduler 测试集中在 policy、final status 和空任务 sealed retry；没有 `_start_due_entries()`、missed-window/restart catch-up、reservation recovery、stats idempotency、跨 reset attribution 测试。

## 待给用户的建议分层

1. 首先修正确性：把 scanner 与 dispatcher 分开，持久化 UTC scan cursor 和 occurrence reservation，使用 `(schedule_id, entry_id, game_day, scheduled_at)` 身份；明确 grace、首次启用、disabled、timezone/DST 语义。
2. 修 retry 提交：通用 manager 改为 retry durable-first；scheduler stats 以 retry metadata 为事实或在 durable retry 后用 retry id 幂等投影，并在启动时 reconciliation。
3. 固定 run game day，由 scheduled occurrence/start 传给 callbacks，不在 attempt 结束时重新计算归属日。
4. correctness 稳定后再抽 `MaaAttemptExecutor/Session`，不要与第一阶段混成一次大改。

## 用户确认的产品语义与方案修正

- 用户确认跨游戏日归属是刻意简化：任务实际在新游戏日完成，对服务器就是新一天的日常；一旦跨日，不继续追逐前一游戏日的未完成目标。此前将其定性为 attribution bug 不成立。
- retry history 是观测数据，不是调度正确性权威；目标是保证运行足量，不为 retry/history 与 stats 建立昂贵的事务协议。
- 用户指出 `RunAttempt` / `evaluate_attempt` 用 attempt 描述 retry，与项目当前术语不一致；后续整理应统一为 retry context/evaluate_retry 等名称，并去除 `attempt_index` 与 `retry_index` 的重复概念。
- 目标抽象是保留 `game_day/tasks/states/retry` 语义的定时运行内核，不是继续泛化 `GenericRunManager`。MAA adapter 负责初始化执行边界、将 task plan 翻译成命令、每轮 retry 前从原始配置生成筛选后的隔离配置、把 MAA raw result 翻译回 task outcome。
- 已核实现有 manual 与 scheduled 都通过 `prepare_maa_cli_task()` 在每轮执行时重新读取原始 task 文件，并按 payload task ids 生成配置；二者真正差异是“下一轮选哪些 task”，不是配置改写机制。因此应共享 `MaaRetrySession`，由 `ManualRetryPolicy` / `ScheduledRetryPolicy` 分别产生 task plan。

## 用户校正后的产品语义与设计方向

- 用户确认跨游戏日重新按当前游戏日处理是刻意简化：跨过 reset 后不应继续追逐前一日未完成事项；即使执行旧需求，服务器侧也只会算作今日行为。不能把 game day 固定到 run 启动日。
- 用户认为 retry 历史是次要观测数据；写入失败不应为了事务一致性阻断执行，核心目标是保证调度任务运行足量。
- 用户指出 `RunAttempt`/`evaluate_attempt` 把一次 retry 称为 attempt，与现有 `LiveRetry`/`RetryDecision` 等主术语冲突。建议整体改为 `RunRetryContext`、`evaluate_retry`、`initial_retry_payload`、`next_retry_payload`，删除与 `retry_index` 重复的 `attempt_index`，MAA generated config 同步使用 `retry-N`。
- 用户倾向抽取一个保留 `game_day/tasks/states` 语义的定时运行基类，并通过 MAA adapter/factory 注入单次执行初始化。

## 完善后的架构判断

- 长生命周期的 `GenericRunManager` 必须仍由 scheduler service 唯一持有，不能由 adapter 每次新建，否则会破坏 current/SSE/stop/同类运行互斥。
- adapter factory 应按一次 scheduled run 创建 `ScheduledExecutorSession`（或 binding），由 scheduler domain runner 组装 `RunStartPlan`。
- scheduler domain runner 拥有 game-day rollover、task policy、daily stats、retry selection/buffer/final status；MAA adapter 拥有 task config 到 scheduler tasks 的映射、command/config generation、collector、raw result、MAA diagnostics/log profile/artifacts。
- rollover 建议显式化：retry 结束时若 game day 已变化，把本次可确认的结果计入当前日，但不携带旧日 `next_task_ids`，结束当前 scheduled run，交给当前日后续 schedule entries。
- daily stats 使用 retry id 作为轻量幂等 execution key 即可，不依赖 retry history 成功；retry history 持久化降为 best effort 并记录日志。

## 环境效果

- 已修改产品代码：统一 retry 术语，新增 `run_manager/context.py` 与 `maa/retry.py`，manual/scheduled 共用 `MaaRetrySession`；同步后端审计与测试。
- 未修改运行配置、未重启服务、未运行 MAA/设备任务。

## 验证

- `uv run pytest ...`：未启动测试，当前 uv 环境没有可生成的 `pytest` console script（`Failed to spawn: pytest`）。
- `.venv/bin/python -m pytest -q tests/test_scheduler_policy.py tests/test_scheduler_run_manager.py tests/test_scheduler_service_status.py tests/test_run_state_and_diagnostics.py -k 'scheduler or scheduled or game_day or daily or final_status'`：11 passed，9 deselected，0.20s。
- 现有通过用例没有覆盖 scanner/due-window/reservation；因此该结果只确认既有 policy/final-status/持久化基本行为未坏，不能反证本轮发现的问题。
- `.venv/bin/python -m pytest -q`：143 passed，6.56s。
- `uvx ruff check src tests`：All checks passed。
- `.venv/bin/python -m compileall -q src tests`、`git diff --check`：通过。
- `typing.get_type_hints()` 已验证 `RetryContext`、`RunCallbacks`、`RunStartPlan` 均可解析。

## 本轮实现

- `RunAttempt` 改为 `RetryContext` 并移入 `run_manager/context.py`；移除重复 `attempt_index`，统一 `evaluate_retry`、`after_retry`、`initial_retry_payload`、`next_retry_payload` 等契约。
- `RetryDecision` 与 callback facade 同处无环 context 边界；顺手修复 manager `Callable` 与 notifications unused import，使 Ruff 清零。
- 新增 `maa/retry.py::MaaRetrySession`，统一每轮源 task 重读、task plan 筛选/force-enable、`retry-N` 生成配置、命令构造、模板 task sequence、raw collector、MaaCore 增量捕捉和 artifacts。
- manual/scheduled callback 只保留各自 task selection、daily stats、buffer 和 final policy；不再各自持有 collector/offset/命令生成实现。
- 新增动态重读行为测试：第二轮修改源 task 参数后，session 读取新值、仍只物化 plan 中的 task，并生成独立 retry-2 文件。

## MaaFramework 官方资料结论

- PI (`interface.json`) 是官方为 General UI 定义的项目 discovery/config contract，包含稳定 task `name`、pipeline `entry`、group、controller/resource applicability、options、presets、imports 和 pipeline overrides。
- MaaFW Core 运行边界是 `Resource + Controller + Tasker`；`post_task(entry, pipeline_override)` 异步返回 task id，status/wait/task detail 提供结构化终态。
- callback protocol 提供 Tasker/Node/Recognition/Action 等结构化事件；PI 的 `focus` 进一步声明 log/toast/notification/dialog/modal 展示语义。未来 WebUI 不应从 stdout 或人类日志反解析任务状态。
- 后续建议把 scheduler 抽象围绕项目无关的 PI task identity + task option snapshot + execution adapter，而不是围绕现有 maa-cli task JSON；当前 `MaaRetrySession` 保持 MAA 专用，作为未来 `ExecutionAdapter` 的一个实现依据。
