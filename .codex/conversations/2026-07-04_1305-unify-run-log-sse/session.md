# Session 2026-07-04_1305-unify-run-log-sse

## Task

Unify scheduler/manual/tool/maintenance run orchestration and decouple task success from visible logs. Change SSE visible-log payloads to match run history retry/run structure, add retry lifecycle markers and simpler patch logic, add run-level status updates, revise timeout semantics, and remove obsolete compatibility.

## Startup

- Read global lessons and memory index.
- Read project history, project lessons, and conversation index.
- Created session folder and scratch directory.

## Notes

- Requirement summary:
  - Backend SSE visible-log payload should become native run/retry/block structure matching history files.
  - Retry completion should seal all blocks, emit a retry-ended marker, reset SSE state, and clear retry-local cache for the next retry.
  - Log entries need `updated_at` and `closed` flags to simplify patching.
  - Add a run-level status update signal/event.
  - Add `max_retries` to run records; when it is `1`, the frontend can ignore retry segmentation.
  - Remove obsolete duplicated run fields such as `created_at`/`started_at` and `log_file`/`log_files` where applicable.
  - Merge manual, scheduled, tool, and maintenance run execution into one orchestration path with hooks for command creation and optional retry cleanup.
  - Keep schedule-specific state handling in `SchedulerService`.
  - Split MaaCore logs per retry only for Maa runs, via an optional retry hook.
  - Replace old six schedule timeouts with generic no-output hang detection and runtime warning/kill thresholds. Manual/tool/maintenance defaults come from settings.
  - Add manual force-stop API/UI behavior after graceful stop is requested.
- Initial implementation plan:
  1. Inspect current run/history/SSE/log buffer data flow and the differences among the four run types.
  2. Define and implement the new run/retry/log entry contract, SSE events, and history write path.
  3. Migrate manual, scheduled, tool, and maintenance execution to a shared retry-capable executor.
  4. Rework timeout and force-stop semantics.
  5. Adjust frontend types, SSE consumer, log panel rendering, and maintenance panel.
  6. Remove old compatibility and unused fields.
  7. Run backend tests plus frontend type/build checks and update persistent project state.

## Implementation Summary

- Added `src/linux_maa/run_executor.py` with shared `LiveRun`, `LiveRetry`, and `RunTimeouts`.
- Reworked `RunStateStore` to persist run records plus per-retry records in `run-retries.json`; history files now store `{run, retries}`.
- Added `updated_at` and `closed` to visible `LogEntry`; retry-local log buffers are sealed at retry completion.
- Reworked SSE patching so state patches carry nested `run` keys and list patches carry `retries`; manual, schedule, tool, and maintenance current panels all expose SSE.
- Migrated manual, scheduled, tool, and maintenance actions to the shared run/retry shape. Manual Maa, scheduled Maa, and tool runs can use configurable `retry_count`; maintenance remains single retry.
- Split MaaCore `asst.log` captures per retry for Maa-backed manual and scheduled runs. Tool and maintenance runs do not use the MaaCore capture hook.
- Replaced old schedule timeout fields with generic no-output, runtime, and stop warning/kill thresholds. Manual/tool/maintenance thresholds come from `framework.run_timeouts`.
- Added manual force-stop endpoint and frontend stop-button transition from graceful stop to destructive force stop.
- Updated frontend types, API normalization, SSE merge logic, LogPane retry rendering, schedule timeout editor, and settings maintenance panel.

## Temporary Assumptions

- No backward compatibility is required for older state/history JSON; old `scheduled-run-attempts.json` and `attempts()` APIs were removed.
- Retry marker rendering can stay minimal for now; complex multi-retry UI is intentionally deferred.
- Maintenance runs use the common process timeout model but do not get a separate force-stop API in this pass.

## Verification

- `uvx ruff check src tests`: passed.
- `uv run python -m compileall -q src tests`: passed.
- `uv run pytest -q`: passed, 48 tests.
- `cd frontend && npx tsc --noEmit --noUnusedLocals --noUnusedParameters --pretty false`: passed.
- `cd frontend && npm run build`: passed; Vite still reports the existing chunk-size warning for the main JS bundle.
- `git diff --check`: passed.

## Environment Effects

- Restarted `linux-maa-webui.service` after the refactor.
- Post-restart health checks:
  - `systemctl status linux-maa-webui.service --no-pager`: active running since 2026-07-04 21:21:43 UTC.
  - `ss -H -ltn sport = :8000`: listening on `0.0.0.0:8000`.
  - `curl -fsS http://127.0.0.1:8000/api/settings`: returned valid JSON including `framework.run_timeouts` and effective timezone `Europe/London` / `UTC+01:00`.

## Follow-up Requirements

- Fully detach task success/failure from `log_entries` and log templates. Visible log templates should no longer own task-result logic.
- Add a raw-line callback interface on live run execution so callers can inspect process output independently. Current needed source is only `maa-cli` stderr.
- Move `task_results` production out of log entries. The two Maa callers, manual and scheduled Maa runs, should own task-result collection.
- Add retry count configuration for manual, scheduled, and tool runs, with retry group fixed to 1. Maintenance stays single-run.
- Manual Maa runs should use scheduled-run-like retry behavior, including skipping child tasks that already succeeded before a retry. Extract shared retry selection logic where practical.
- Retry-count input should sit beside the stop button and persist with the page/UI state, not with task config or tool type config.
- Manual-triggered scheduled runs need the same graceful-stop/force-stop button logic. Extract a shared frontend stop button component.
- Normalize frontend time display to browser-local timezone and consistent HH:MM:SS durations/timestamps.
- Schedule recent-runs list needs a delete button shown only when force/delete controls are visible, and a badge distinguishing manual-triggered versus timed-triggered schedule runs.
- Settings page maintenance log should be a small hidden-by-default right-column panel like before, without a header, not a large standalone card.
- Remove the Settings left-column scheduler enabled config; the schedule page already owns that switch.

## Follow-up Implementation Summary

- Added `RawLineCallback` to `run_streaming_process()` and wired Maa manual/scheduled runs to consume only `maa-cli:stderr` raw lines through `MaaTaskResultCollector`.
- Removed task-result projection and task-sequence APIs from the visible log pipeline. `LogEntry`/templates now only represent UI-visible log blocks; `task_results` live on `LiveRetry`/history retry records.
- Added configurable retry counts for manual Maa, manual-triggered scheduled runs, automatic schedule config, and tool runs. Retry group size is fixed to one; maintenance remains single retry.
- Manual Maa retries now use the same task selection helper as scheduled retries: already successful child tasks in the current run are skipped before the next retry config is generated.
- Added force-stop APIs for schedule and tool current runs, plus a shared frontend `RunStopButton` used by manual, schedule, and tool pages.
- Added page-local retry-count inputs beside run/stop controls on manual, schedule, and tool pages, persisted in `localStorage`.
- Added browser-local frontend time formatting in `frontend/src/lib/time.ts`; log times and schedule history timestamps now use the shared helpers.
- Added schedule recent-run delete action and manual/timed trigger badges; `RunStateStore.delete_run()` removes the run record, retry records, and durable history file.
- Moved settings maintenance logs back into a small hidden-by-default right-column panel using shared `LogPane` without a header, and removed the settings left-column scheduler enabled checkbox.

## Session Mistakes

- First post-restart health check used bare `python -m json.tool`; this machine has no `python` executable. Re-ran with `python3 -m json.tool` successfully. The global lesson already records this machine-level trap.

## 2026-07-05 Follow-up

- Replaced schedule retry-group wording with buffer semantics: `retry.buffer_every_retries` and `retry.buffer_seconds`. The scheduler waits after every configured N completed retry segments only when another retry remains; stop requests wake the wait early.
- Reworked schedule timeout/retry settings UI into three titled rows: retry config, warning thresholds, and force-stop thresholds.
- Added visible two-line `重试/次数` labels beside the manual, scheduled, and tool stop buttons; narrowed the retry count inputs.
- Schedule recent-run cards now place time first in the lower metadata line and use a compact right-side icon button group.
- Log entry lifecycle fields are now `opened_at`/`sealed_at`; run/retry lifecycle fields remain `started_at`/`ended_at`. Backend-created visible log timestamps are offset-aware server-local ISO strings, and API/SSE requests send browser timezone data.
- Verification after this follow-up: `uvx ruff check src tests`, `uv run python -m compileall -q src tests`, `uv run pytest -q` (48 tests), `cd frontend && npx tsc --noEmit --noUnusedLocals --noUnusedParameters --pretty false`, `cd frontend && npm run build`, and `git diff --check` passed.
- Restarted `linux-maa-webui.service`; active since 2026-07-05 02:38:04 UTC, listening on `0.0.0.0:8000`, `/api/settings` returned `Europe/London` / `UTC+01:00` with client timezone headers.
- Adjusted the three retry-count controls beside stop buttons again: removed fixed input height, narrowed the number input, and used a slightly larger label/input gap so the label is not glued to the field. Verification: `cd frontend && npx tsc --noEmit --noUnusedLocals --noUnusedParameters --pretty false`, `cd frontend && npm run build`, and `git diff --check` passed. Restarted `linux-maa-webui.service`; active since 2026-07-05 03:11:24 UTC and listening on `0.0.0.0:8000`.
