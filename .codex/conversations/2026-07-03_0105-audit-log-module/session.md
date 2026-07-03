# Session 2026-07-03_0105-audit-log-module

## Task

- Inspect the latest session's claim about unifying WebUI-visible log functionality outside maa run logic.
- Explain why `class MaaCliLogTranslator` still exists.
- Further extract and abstract WebUI-visible logging after user requested implementation.
- Audit how schedule restart-script output is handled and wire it into the shared visible log system.

## Startup Context

- Read global lessons, global memory index, project history, project lessons, and project conversation index.
- Latest prior session from the project conversation index is `2026-07-02_2245-tools-page`.

## Findings

- Confirmed: `2026-07-02_2245-tools-page` unified tool visible logs with the existing maa-cli visible-log translator path, but did not move the translator module out of `linux_maa.maa.logs`.
- Confirmed: `src/linux_maa/maa/logs/translator.py` still defines `MaaCliLogTranslator`.
- Confirmed: manual runs, scheduled runs, and tool runs all instantiate the same translator class and expose `output`, `task_results`, and `log_entries` through their current-run states.
- Confirmed: `src/linux_maa/tools/manager.py` imports `MaaCliLogTranslator` from `linux_maa.maa.logs`, so a non-maa tool manager still depends on a maa-namespaced visible-log module.
- Confirmed: maintenance actions still expose only raw `output` and do not use `log_entries`/`MaaCliLogTranslator`, even though their output is WebUI-visible.
- Conclusion: the latest session achieved shared visible-log behavior for manual/scheduled/tool runs, but did not fully achieve the stricter architecture goal of putting all WebUI-visible log functionality in a module outside maa run logic.

## Implementation

- Moved the logging implementation from `src/linux_maa/maa/logs/` to top-level `src/linux_maa/logs/`.
- Renamed the concrete translator class to `RunLogTranslator`; `linux_maa.maa.logs.MaaCliLogTranslator` now exists only as a compatibility alias.
- Added `RunLogBuffer` as the shared holder for bounded `output`, `task_results`, and `log_entries`.
- Updated manual runs, scheduled runs, tool runs, and maintenance actions to use `RunLogBuffer`.
- Maintenance actions now return `log_file`, `log_files`, `task_results`, and `log_entries` in addition to `output`; Settings page types were updated accordingly.
- Added a plain parser path via `RunLogTranslator.translate_plain()` so arbitrary script output is visible as line entries without triggering MAA summary/task grouping.
- Changed schedule restart-script hooks from `ScheduleScriptManager.run(... subprocess.run(capture_output=True) ...)` to `ScheduleScriptManager.command()` plus `run_streaming_process()` in `SchedulerService`.
- Schedule restart-script stdout/stderr now stream live into the scheduled run's visible log and are stored in `debug/linux-maa/external/scripts/<run-id>.stdout.log` / `.stderr.log`.
- Schedule scripts now run with `MaaRuntime.env()`, so project-local `maa`, `MAA_CONFIG_DIR`, and XDG paths are available inside hooks.
- Updated `README.md`, `docs/maa-runtime.md`, and `docs/architecture-direction.md` for the new log module and script-output behavior.

## Script Output Answer

- Before this change, schedule restart-script output was captured synchronously with `subprocess.run(..., capture_output=True)` and appended only after script completion as framework events. It did not stream live, did not have separate stdout/stderr diagnostics, and was only partially visible through `log_entries` because `_append_event()` used the maa-cli translator event path.
- After this change, restart-script stdout/stderr stream live through the same WebUI-visible log buffer using the plain parser and have separate diagnostics under `debug/linux-maa/external/scripts/`.

## Commands

- `rg -n "MaaCliLogTranslator|maa\\.logs|log_entries|translate\\(" src tests frontend/src -g '!frontend/node_modules/**'`
- `rg --files src/linux_maa | sort`
- `sed`/`nl` inspections of `src/linux_maa/maa/logs/translator.py`, `src/linux_maa/maa/runner.py`, `src/linux_maa/scheduler/service.py`, `src/linux_maa/tools/manager.py`, and `src/linux_maa/maa/maintenance.py`.
- `uv run python -m compileall -q src tests`
- `uv run pytest tests/test_maa_logs.py tests/test_backend_utilities.py tests/test_run_state_and_diagnostics.py -q`: passed 30 tests.
- `uv run pytest -q`: passed 45 tests.
- `cd frontend && npm run build`: passed with existing Vite >500 kB chunk warning.
- `git diff --check`: passed.
- Restarted `linux-maa-webui.service`; first immediate curl hit the restart window, then status showed active and port 8000 listening. `GET /api/tools` and `GET /api/maintenance/current` returned successfully.

## Environment Effects

- Created session directory `.codex/conversations/2026-07-03_0105-audit-log-module/` with `scratch/`.
- Restarted the active systemd unit `linux-maa-webui.service` so the new backend/frontend build is served. During restart, systemd waited for open connections to close, hit the stop timeout, SIGKILLed the old process group, then started a healthy new Uvicorn process. The unit is active and listening on `0.0.0.0:8000`.

## Session Lessons

- `linux-maa-webui.service` can spend the stop timeout waiting on existing SSE/browser connections during restart; an immediate curl can fail before the replacement Uvicorn process starts. Verify with `systemctl status`, `ss`, or retry curl after restart.
