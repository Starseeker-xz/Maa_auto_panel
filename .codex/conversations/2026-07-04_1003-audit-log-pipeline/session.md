# Session 2026-07-04_1003-audit-log-pipeline

## Goal

- Audit recent log pipeline improvements, especially extracted common block logic.
- Inspect the latest scheduled execution and add log translation/color behavior for expiring medicine and a neutral theme-highlight level.

## Startup

- Read `~/.codex/lessons.md`.
- Read `~/.codex/memories/index.md`; no related detailed global memory loaded.
- Read project history, project lessons, and conversation index.

## Findings

- Confirmed: latest scheduled execution `e94016514899` ended at `2026-07-04T09:18:21` with final status `failed` in `state/linux-maa/run-history/recent-run-records.json`; it is not actively running.
- Confirmed: `history/linux-maa/runs/schedules/daily-test/e94016514899.json` had a stale top-level `run.status="running"` because per-attempt history writes embedded the run snapshot before final `finish_run()`, and finish did not sync that embedded snapshot.
- Confirmed: the `failed` final status for `e94016514899` was also incorrect. Attempt 5 succeeded for the remaining retry tasks. `剿灭` failed earlier, but retry policy deferred it because later enabled schedule slots remained; `_final_status()` ignored those future slots and treated the current run as failed.
- Confirmed: latest raw logs include untranslated `Use 1 expiring medicine` and summary lines such as `Fight 1-7 72 times, used 4 medicine (4 expiring), drops:`.
- Confirmed: recent block-pipeline extraction left a type/schema mismatch: backend metadata accepted `status_override="warning"` and tests used it, while `BlockStatus` omitted `warning`; frontend also omitted `unfinished` from the status union.

## Changes

- Added `theme` log tone for neutral theme-color structure highlighting.
- Translated and highlighted:
  - `Current sanity: 17/210` -> `当前理智: 17/210` (`theme`)
  - `Mission started (...)` -> `开始行动 (...)` (`theme`)
  - `Use 1 expiring medicine` -> `使用 1 个临期理智药` (`warning`)
  - `Use N medicine` -> `使用 N 个理智药` (`warning`)
  - summary `Fight ... used ... medicine (... expiring), drops:` lines
  - summary numbered rows, including public-recruit tag rows and drop rows, plus `total drops` rows (`theme`)
- Added `RunStateStore._sync_run_history()` and call it from `finish_run()` and `finish_generic_run()` so future history files sync top-level `run` after final status.
- Updated scheduler `_final_status()` to consider remaining enabled schedule slots for important finite daily-success tasks, matching `retry_task_ids()` behavior. A deferred unmet important task no longer fails the current run while enough future slots remain.
- Corrected local state for existing run `e94016514899`: recent index and per-run history top-level run now show `status=succeeded` / `summary.final_status=succeeded`; attempt records were left unchanged.
- Updated frontend tone/status unions and `LogPane` class maps for `theme`, `warning`, and `unfinished`.
- Added generic LogPane historical-log mode:
  - `historyRun` displays archived entries instead of current stream while current run state continues updating in the background.
  - status pill becomes yellow `历史日志`.
  - header shows `关闭历史日志`, or `返回当前日志` when a run is active.
  - header spacing was tightened and vertically centered.
- Wired historical-log loading only in the schedule page: recent schedule runs now show a hover/focus `查看历史日志` icon button, using `/api/history/runs/{run_id}` and merging attempt `log_entries` into the panel view.
- Fixed LogPane header after feedback: status pill is again below the title; header padding remains tightened and content is vertically centered.
- Fixed scheduler stop deadlock: `SchedulerService.stop_current()` could call `_append_framework_event()` while holding a non-reentrant `_lock`, and `_append_framework_event()` re-entered the same lock through `_mark_log_updated()`. `_lock` is now an `RLock`.
- Added startup recovery for persisted `running` / `stopping` run records. After restart, stale in-progress records are marked `stopped` with `summary.recovered_reason`. This recovered `95e5d01578a8`.

## Verification

- `uv run pytest tests/test_maa_logs.py tests/test_run_state_and_diagnostics.py -q` -> 27 passed.
- `uv run pytest tests/test_scheduler_policy.py tests/test_scheduler_service_status.py -q` -> 9 passed.
- `uv run python -m compileall -q src tests` -> passed.
- `uv run pytest -q` -> 54 passed.
- `cd frontend && npm run build` -> passed, with existing Vite chunk-size warning.
- `uv run python -m compileall -q src tests && uv run pytest tests/test_run_state_and_diagnostics.py tests/test_scheduler_service_status.py -q` -> 7 passed after deadlock fix.
- `systemctl restart linux-maa-webui.service` -> restarted; `/api/schedules` returned `enabled=True`, 7 recent runs, 1 schedule.
