# Session 2026-07-01_2153-manage-service-history

## Scope

- Stop the currently running Linux MAA WebUI without manual PID searching.
- Register a temporary systemd service for start/stop management.
- Verify unresolved issues recorded in project history.

## Initial Observations

- Confirmed: Global lessons include a prior `pgrep`/`pkill -f` trap in this environment; avoid command-line PID searches for service cleanup.
- Confirmed: Project history says WebUI was previously launched via detached `setsid uv run linux-maa webui --host 0.0.0.0 --port 8000`.
- Confirmed: `runtime/linux-maa/webui.pid` currently contains `4`, but `ps` shows no corresponding process, so the old PID file is stale.
- Confirmed: systemd is available and reports the system as `running`.

## Environment Effects

- Confirmed: Stopped the legacy WebUI listener on port 8000 after verifying `127.0.0.1:8000/api/settings` belonged to this project.
- Confirmed: Registered temporary systemd unit `/etc/systemd/system/linux-maa-webui.service`.
- Confirmed: Unit command is `/root/.local/bin/uv run linux-maa webui --host 0.0.0.0 --port 8000`, working directory `/root/Linux_maa`.
- Confirmed: Ran `systemctl daemon-reload`; `systemd-analyze verify /etc/systemd/system/linux-maa-webui.service` passed.
- Confirmed: Service is currently registered, `disabled`, and `inactive`; port 8000 is free.
- Confirmed: Removed stale ignored runtime PID file `runtime/linux-maa/webui.pid`.

## Verification

- `curl -sS --max-time 2 http://127.0.0.1:8000/api/settings`: returned project settings before shutdown, confirming port 8000 belonged to Linux MAA WebUI.
- `ss -H -ltn sport = :8000`: no output after shutdown, confirming no listener on 8000.
- `systemctl status linux-maa-webui --no-pager`: service loaded from `/etc/systemd/system/linux-maa-webui.service`, inactive.
- `systemctl is-enabled linux-maa-webui`: `disabled`.
- `npm run build` in `frontend/`: passed; Vite still reports the existing 500 kB chunk warning with `index-DvZApfPE.js` at 752.15 kB minified / 240.10 kB gzip.

## Project-History Pending Issues Checked

- Confirmed: `SettingsPage` remains large at 658 lines.
- Confirmed: `PrimitiveArrayEditor` remains dense at 390 lines.
- Confirmed: dirty/deep equality still uses `JSON.stringify` in `SettingsPage`, `SchedulePage`, and `ConfigEditorPane`.
- Confirmed: frontend bundle warning still reproduces in `npm run build`.
- Superseded: initial check found live `log_entries` unbounded in translator/task/summary/message lists; later in this session `MaaCliLogTranslator` was changed to bound structured entries/task records/messages/raw lines.

## Framework Logging Rework

- Confirmed: User rejected a DB-backed design for lightweight framework state; use text/JSONL instead.
- Confirmed: User requested framework log/history output under the project-root `debug/` tree and asked not to hardcode paths. Added registered `MaaRuntime` paths for framework config and framework logs.
- Superseded: Replaced scheduler SQLite persistence with text-backed `RunHistoryStore` under `debug/linux-maa/history/`. User later rejected this because state does not belong under disposable `debug/`.
- Superseded: Added global detailed framework log `debug/linux-maa/framework.log` by mirroring framework events. User later rejected this because framework debug must be real Python logging, not an events copy.
- Superseded: High-level run events were JSONL under `debug/linux-maa/events/<kind>/<run-id>.jsonl`; current corrected path is `debug/linux-maa/events/<run-id>.jsonl`.
- Superseded: Per-run child process detail logs were text under `debug/linux-maa/logs/<kind>/`; current corrected path is source-based `debug/linux-maa/external/maa-cli/<run-id>.*.log`.
- Confirmed: `run_maa_cli_process()` now reads stdout and stderr separately. Per-run detailed logs store maa-cli stdout and stderr in physically separate `*.stdout.log` / `*.stderr.log` files; UI parsing still receives an ordered merged view.
- Superseded: MaaCore run deltas were stored under `debug/linux-maa/maacore/<kind>/<run-id>.log`; current corrected path is source-based `debug/linux-maa/external/maacore/<run-id>.log`.
- Confirmed: `MaaCliLogTranslator` now bounds in-memory structured entries/task records/messages/raw lines. Detailed diagnosis belongs in text logs, not unbounded UI state.
- Verification: `uv run python -m compileall -q src tests` passed.
- Verification: `uv run pytest -q` passed 31 tests.
- Verification: Initial `npm run build` from repo root failed because the frontend package is under `frontend/`, not root. Reran as `npm run build` in `/root/Linux_maa/frontend`; it passed with only Vite's standard chunk-size warning.

## Framework Logging/State Correction

- Confirmed: User rejected the intermediate `RunHistoryStore` design because it mixed runtime state, scheduler bookkeeping, high-level JSONL events, framework debug, maa-cli logs, MaaCore captures, and retention in one class.
- Confirmed: Deleted `src/linux_maa/history.py`. Added `src/linux_maa/storage/files.py` for basic text/JSON primitives, `src/linux_maa/run_state.py` for state, and `src/linux_maa/diagnostics.py` for logging/diagnostics.
- Confirmed: State now lives outside `debug/` under `state/linux-maa/`: `run-history/recent-run-records.json`, `run-history/scheduled-run-attempts.json`, `scheduler/daily-task-stats.json`, and `scheduler/triggered-schedule-entries.json`.
- Confirmed: Diagnostics now live under `debug/linux-maa/`: `framework.log` uses Python `logging` with DEBUG/INFO/WARNING/ERROR/CRITICAL; API requests are logged by FastAPI middleware; human-level run events are JSONL under `events/<run-id>.jsonl`.
- Confirmed: External logs are grouped by source rather than manual/scheduled origin: maa-cli stdout/stderr under `debug/linux-maa/external/maa-cli/<run-id>.stdout.log` and `<run-id>.stderr.log`; MaaCore `asst.log` deltas under `debug/linux-maa/external/maacore/<run-id>.log`.
- Confirmed: Removed stale local `debug/linux-maa/` artifacts generated by the rejected layout so the next service start creates only the new layout.
- Verification: `uv run python -m compileall -q src tests` passed after the correction.
- Verification: `uv run pytest -q` passed 33 tests after the correction.
- Verification: `npm run build` in `/root/Linux_maa/frontend` passed after the correction, with only Vite's existing chunk-size warning.
