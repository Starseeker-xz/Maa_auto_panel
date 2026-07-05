# Session 2026-07-05_1823-check-history-chunking

## Task

User reported that a currently running scheduled history showed MAA task lifecycle/detail lines as separate cards instead of task blocks, then reported that manual force-stop appeared to do nothing.

## Findings

- Confirmed: run `f7ecfac6dafc` (`daily-test`, entry `t1600`, started `2026-07-05T18:00:02+00:00`) had `log_entries` mostly as fallback `kind="line"` blocks. `StartUp Start`, `StartUp Completed`, `Infrast Start`, and Infrast detail lines did not hit `maa-task-lifecycle`.
- Confirmed: raw stderr for `f7ecfac6dafc` contained normal MAA lifecycle lines. The failure was in visible log block-rule registration, not maa-cli output.
- Confirmed: current worktree had removed visible task block registration from `maa/log_templates.py` during the LiveRun/LiveRetry + task-result collector refactor. `HEAD` still had `maa-task-lifecycle`; the regression was in the uncommitted refactor state.
- Confirmed: `MaaTaskResultCollector` still produced retry-local task results, but only from lifecycle start/end lines; it intentionally did not drive UI visible blocks.
- Confirmed: stop/force-stop issue was state-machine related, not an alive maa-cli process. `ps` showed no maa-cli child. API returned `status="stopping"` with `ended_at="2026-07-05T18:24:02+00:00"` after the run had already logged `scheduled run finished ... status=stopped`.
- Confirmed: force-stop after terminal state called `LiveRun.request_force_stop()`, which changed an already finished run back to `stopping`.
- Confirmed: schedule retry buffer events after retry 3 created a fourth open retry log segment for "缓冲等待/停止请求" events; finish did not seal that log-only retry, so live state could keep a running retry segment after the run ended.
- Confirmed: schedule metadata included `retry_count=max_retries`, and `LiveRun.run_dict()` let metadata override computed `retry_count=len(retries)`, producing misleading `retry_count=12`.

## Changes

- Restored MAA visible `maa-task-lifecycle` block rule while keeping `MaaTaskResultCollector` as the authoritative retry/final-status source.
- Reintroduced task-sequence display hooks (`begin_task_sequence`) only for visible log naming, without restoring old projected `task_results`.
- Manual and scheduled Maa attempts now pass the retry's expected task descriptors to the visible log buffer before maa-cli starts.
- Made terminal `LiveRun.request_stop()` / `request_force_stop()` idempotent; terminal runs no longer switch back to `stopping`.
- `SchedulerService.stop_current()` / `force_stop_current()` return terminal current runs unchanged instead of appending new stop events.
- Schedule finish now seals and persists any current log-only retry segment before finishing the run.
- `LiveRun.run_dict()` no longer lets metadata keys override core fields such as computed `retry_count`.

## Verification

- `uv run pytest -q tests/test_maa_logs.py tests/test_backend_utilities.py` — 31 passed.
- `uv run python -m compileall -q src tests` — passed.
- `uv run pytest -q` — 51 passed.
- `uvx ruff check src tests` — passed.
- Replayed real `debug/linux-maa/external/maa-cli/f7ecfac6dafc.stderr.log` through `RunLogBuffer`: output included task blocks for `启动 B 服` and `基建换班`, with Infrast details grouped under the task block.
- `cd frontend && npx tsc --noEmit --noUnusedLocals --noUnusedParameters --pretty false` — passed.
- `git diff --check` — passed.
- `cd frontend && npm run build` — passed; Vite still warns about the existing >500 kB chunk.

## Environment Effects

- Restarted `linux-maa-webui.service` at `2026-07-05T18:37:13+00:00` to apply backend fixes.
- Confirmed service active afterward and `/api/schedules/current` returned idle (`run.status="idle"`, `stream_version=0`).
- Confirmed `/api/schedules/daily-test` recent run `f7ecfac6dafc` persisted as `status="stopped"`, `retry_count=3`, summary `final_status="stopped"`.
