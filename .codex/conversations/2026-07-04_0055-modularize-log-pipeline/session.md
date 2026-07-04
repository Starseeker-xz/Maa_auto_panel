# Session 2026-07-04_0055-modularize-log-pipeline

## Goal

Implement the visible log pipeline modularization plan:

- Single block-shaped `log_entry`.
- Source-specific split/translation templates registered by callers.
- MAA-specific log translation moved out of `logs/`.
- Events flow through the same visible log pipeline.
- Raw text stream persistence remains in `Diagnostics`.

## Notes

- Compatibility with old `line`/`task`/`summary` log entry union is intentionally not preserved.
- Session started after the planning turn; initial `.codex` reads were completed before implementation.

## Implementation Summary

- Replaced old `RunLogTranslator` architecture with generic `LogPipelineSession`, `LogSourceSpec`, plain/event templates, and single block-shaped `LogEntry`.
- Removed `src/linux_maa/logs/translator.py`, `rules.py`, and `translation.py`.
- Moved MAA-specific translation and block assembly into `src/linux_maa/maa/log_templates.py`.
- Kept raw stdout/stderr persistence in `Diagnostics`; managers still write diagnostics first and visible log pipeline second.
- Manual runs, scheduler runs, maintenance actions, and tools now register visible-log sources explicitly.
- Scheduler child timeout query now uses block elapsed time: `current_block_elapsed_seconds(kind="task")`.
- Frontend `MaaLogEntry` is now a single block type, and `LogPane` renders by `kind/status/messages`.
- Updated docs/tests for the new shape.

## Verification

- `uv run python -m compileall -q src tests` passed.
- `uv run pytest -q` passed: 42 tests.
- `cd frontend && npm run build` passed with the existing Vite chunk-size warning.

## Follow-up Fix

- User observed no visible run summary for manual run `5682a45220e1`.
- Root cause: stdout emitted `Already up to date.` before `Summary`; `MaaLogTemplate` opened a git/resource block and absorbed subsequent no-timestamp `Summary` lines into that resource block.
- Fixed `MaaLogTemplate.handle_line()` so `Summary` closes any current git block and starts a run-summary block.
- Added regression `test_summary_after_git_up_to_date_starts_run_summary_block`.
- Revised persistence after user feedback: generic manual/tool/maintenance runs now call `RunStateStore.add_single_attempt()`, which reuses the same attempt-record path as scheduled attempts with fixed `attempt_index=1` and `retry_group=1`. `log_entries` are no longer duplicated into generic run `summary`.
- Resource update block handling now treats `Summary` as the fixed boundary after either `Already up to date.` or an `Updating ...` / `Fast-forward` git diff block.
- User clarified `From https://github.com/...` belongs to stderr fetch diagnostics, not stdout resource changes. Updated rules:
  - stdout resource-change block starts only on `Already up to date.` or `Updating <sha>..<sha>` and ends at `Summary`.
  - stderr `From https://github.com/...` starts a separate resource-fetch diagnostic block.
- Verification after fix: `uv run python -m compileall -q src tests` passed; `uv run pytest -q` passed with 46 tests; frontend build passed with existing chunk warning.
- User tested manual run `e0406fc58549` before the updated persistence code was loaded by the systemd WebUI process. `scheduled-run-attempts.json` had no attempt for that run because the running service was still the old process.
- Restarted `linux-maa-webui.service` at 2026-07-04 01:47 UTC. New server PID observed: 26225. This is an active environment effect.

## History Persistence Revision

- User requested that log blocks should not live under `state/`, and that schedule attempts should be split by schedule/run instead of a single `scheduled-run-attempts.json` carrying all blocks.
- Added `MaaRuntime.framework_history_dir` / `run_history_dir` under `history/linux-maa/runs`.
- `scheduled-run-attempts.json` is now only an attempt index with `log_entries_file`; visible log blocks are written to durable history files:
  - schedule: `history/linux-maa/runs/schedules/<schedule-id>/<run-id>.json`
  - manual: `history/linux-maa/runs/manual/<run-id>.json`
  - tool: `history/linux-maa/runs/tools/<tool-id>/<run-id>.json`
  - maintenance: `history/linux-maa/runs/maintenance/<kind>/<run-id>.json`
- `RunStateStore.attempts(run_id)` hydrates `log_entries` from the referenced history file so the API shape remains useful.
- Fixed a `diagnostics -> maa.__init__ -> maintenance -> diagnostics` import cycle by making the `MaaRuntime` import type-checking-only in `diagnostics.py`.
- Verification: `uv run python -m compileall -q src tests`, `uv run pytest -q` (46 tests), and frontend build passed.
- Restarted `linux-maa-webui.service` at 2026-07-04 02:03 UTC. New server PID observed: 39932.
