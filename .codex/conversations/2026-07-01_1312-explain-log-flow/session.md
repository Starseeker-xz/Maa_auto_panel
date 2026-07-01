# Session 2026-07-01_1312-explain-log-flow

Task: Explain current log translation/display logic, especially how logs are chunked and how frontend responds.

Observed:
- Manual runs and scheduled runs both use `MaaCliLogTranslator`.
- `run_maa_cli_process()` reads stdout plus tails the maa-cli log file when enabled, forwarding text chunks to the translator.
- Translator buffers incomplete physical lines, then groups complete lines into `line`, `task`, or `summary` entries.
- Before the SSE change, frontend polled current run state every 1000 ms; there was no websocket/SSE path for logs.
- `LogPane` prefers structured `run.log_entries`; it only falls back to splitting `run.output` when structured entries are missing.

Changes made:
- Replaced previous monolithic `src/linux_maa/maa/logs.py` with a `src/linux_maa/maa/logs/` package:
  - `records.py`: structured output dataclasses and log/status/tone types.
  - `translation.py`: global/task/summary translation helpers.
  - `rules.py`: explicit panel/chunk rules, including summary, task lifecycle, and default line rules.
  - `translator.py`: stateful translator orchestration.
  - `__init__.py`: compatibility exports, so existing `from linux_maa.maa.logs import MaaCliLogTranslator` callers continue working.
- Preserved current API/output behavior: `log_entries` still contains top-level `line`, `task`, and `summary`; default line matching becomes a rule, while lines inside an active task still append to the active task's `messages` as before.
- User clarified the desired refactor style: related internals should be wrapped in a domain package, not scattered across the parent directory. Promoted this as a project lesson.

Verification:
- `uv run python -m compileall -q src tests`: passed.
- `uv run pytest tests/test_maa_logs.py -q`: 8 passed after package migration.
- `uv run pytest -q`: 26 passed after package migration.

Follow-up output batching:
- Clarified current `process.py` behavior: stdout is read with `readline()` after `select()`, so it submits whole stdout lines, not individual characters; log-file tail submits all newly appended bytes from the file each loop.
- Optimized `run_maa_cli_process()` so each loop batches stdout and log-file chunks into at most one `on_output()` call, and does the same final batching on process exit.
- Verification after batching: `uv run python -m compileall -q src tests` passed; `uv run pytest -q` passed with 26 tests.

Follow-up log-file source correction:
- Upstream `docs/maa-upstream/zh-cn/manual/cli/usage.md` says maa-cli logs to stderr by default, and `--log-file` only also writes logs to a file. Since `process.py` already merges stderr into stdout, tailing the saved log file was redundant and risked duplicate live logs.
- First correction removed live tailing of `--log-file`, but a real `startup-smoke` run showed that with the current `maa-cli v0.7.5`, passing `--log-file` caused info lifecycle logs (`StartUp Start/Completed`) to appear only in the file, while stderr/stdout contained only git/update text and Summary. That produced `task_results=[]`.
- Final correction: WebUI/scheduled live runs no longer pass `--log-file` to maa-cli. `run_maa_cli_process()` reads only merged stdout/stderr and optionally tees that same stream into the framework-owned `state.log_file` artifact.
- Set `MAA_LOG_PREFIX=Always` in `MaaRuntime.env()` so stderr logs retain the timestamp/level prefix expected by the structured parser even if the host environment differs.
- Real verification: `startup-smoke` WebUI/manual manager path succeeded on run `18e8db502e5c`. It produced `StartUp` task entry/status `succeeded`, `return_code=0`, and tee log file `runtime/maa/run-logs/20260701-140848-startup-smoke-webui.log`.

SSE change:
- Added backend SSE helper `src/linux_maa/web/sse.py`.
- Added `GET /api/runs/current/events` and `GET /api/schedules/current/events`.
- Replaced `MainPage` and `SchedulePage` 1-second current-run polling with `EventSource`; settings maintenance polling remains on `usePolling`.
- SSE streams send the current state immediately and then send complete `RunState` payloads only when a state signature changes.
- Real HTTP verification against local uvicorn on port 8765: idle events worked for manual/schedule streams; starting `startup-smoke` through `POST /api/runs` produced streamed events through two tasks and final `succeeded`.
- Browser verification against the built frontend at local uvicorn port 8765 passed for `/` and `/schedule` with no console/page errors. Initial Playwright `networkidle` wait timed out because SSE keeps the connection open; reran successfully with `domcontentloaded`.
