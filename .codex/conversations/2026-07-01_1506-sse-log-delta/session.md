# Session 2026-07-01_1506-sse-log-delta

## Task

- Continue the previous log SSE work.
- Improve the current implementation from SSE pushing full log/current payloads to a pattern of one initial full fetch plus SSE incremental pushes.
- Audit the affected log/current-state module before modifying it, and actively surface architectural risks instead of only making narrow requested fixes.
- Record the project-level execution policy in durable project state and a root markdown document.

## Startup

- Confirmed: repository path is `/root/Linux_maa`.
- Confirmed: working tree was clean at session start.
- Confirmed: read global lessons, global memory index, project history, project lessons, and conversation index.

## Active Environment Effects

- Restarted WebUI on `http://0.0.0.0:8000/`.
- PID file `runtime/linux-maa/webui.pid` now contains wrapper PID `48258`.
- Server log remains `runtime/linux-maa/webui.log`.

## Audit Findings

- Confirmed: previous SSE endpoints woke on version changes, but every data event still called full `to_dict()`, repeatedly sending `output`, `task_results`, and `log_entries`.
- Confirmed: `task_results` and `log_entries` contain mutable tail objects. A naive append-only diff by array length would miss task status changes, task messages, and summary messages.
- Confirmed: scheduler overview/detail responses embedded current-run log arrays even though those routes are configuration/overview reads, not log streaming routes.
- Confirmed: after the SSE delta change, backend persisted `StartUp Start` at `15:19:49` in `runtime/maa/run-logs/20260701-151941-startup-smoke-webui.log`, but the log pane had no follow-tail behavior. New entries could land below the visible scroll area, making it look like the log did not update until a later refresh/reflow.
- Likely: live `log_entries` remains unbounded in memory; fixing that cleanly requires separating realtime display retention from persistent run/attempt records, so it was recorded as a future log-retention concern rather than mixed into this streaming patch.

## Implementation Summary

- Added versioned current snapshots with `stream_version`.
- Changed run and schedule SSE endpoints to emit `patch` events with array `replace_from/items`, plus `reset` only when no cursor or recovery requires it.
- Changed frontend Main and Schedule pages to fetch one full current snapshot, open EventSource with version/array cursors, and merge incremental patches locally.
- Added follow-tail behavior to `frontend/src/pages/main/LogPane.tsx`; the log view now scrolls to the newest entry while the user is already near the bottom, and stops auto-scrolling when the user manually scrolls up.
- Changed scheduler overview/detail current-run payloads to use light current state without log arrays.
- Added `PROJECT_EXECUTION_POLICY.md` and a project lesson for the requested audit-first execution policy.

## Verification

- Passed: `uv run python -m compileall -q src tests`.
- Passed: `uv run pytest -q` with 28 tests.
- Passed: `cd frontend && npm run build`; only the existing Vite large chunk warning remained.
- After the LogPane follow-tail fix, repeated `uv run pytest -q` and `cd frontend && npm run build`; both still passed.
- Smoke: `GET /api/runs/current` returned `{"status":"idle","output":[],"stream_version":0}` after restart.
- Smoke: `GET /api/schedules/current` returned `{"status":"idle","output":[],"stream_version":0}` after restart.
- Smoke: `timeout 2 curl -sSN 'http://127.0.0.1:8000/api/runs/current/events?after=0&output_from=0&task_results_from=0&log_entries_from=0'` produced no data before timeout, confirming no immediate full SSE payload when the client is already at the current version.
- Smoke: `GET /` from the running WebUI now serves `assets/index-DvZApfPE.js`, the bundle containing the follow-tail fix.

## Mistakes

- A restart script used `pgrep -f '[l]inux-maa webui ...'` before a later literal `setsid uv run linux-maa webui ...` line. The `pgrep` matched the current shell command and the script killed itself. Recorded a global lesson; safer pattern is separate cleanup/start commands or PID/port-owner targeting.

## Notes

- Need avoid Playwright `networkidle` for SSE pages; use `domcontentloaded` and targeted checks.
