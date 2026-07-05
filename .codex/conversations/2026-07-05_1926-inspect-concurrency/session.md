# Session 2026-07-05_1926-inspect-concurrency

## Question

- User asked whether the current framework has mutual-exclusion/preemption handling for two runs happening at once, and whether timed scheduled runs handle the case where a previous scheduled run is still running when a new one is due.

## Initial Findings

- Confirmed: There is no global cross-kind run arbiter. `WebServices` wires separate managers for manual Maa runs, maintenance actions, tools, and scheduled runs.
- Confirmed: Manual Maa runs block only another manual run with current status exactly `running`; they do not block scheduled/tool/maintenance runs, and do not block a new manual run while the old current run is already `stopping`.
- Confirmed: Scheduler has per-scheduler mutual exclusion. Automatic loop skips due-entry scanning while the scheduler current run is `running` or `stopping`; `_start_run()` also rejects another scheduled run in those states.
- Confirmed: Timed scheduled conflicts are not queued or used to stop/preempt the old scheduled run. If the previous scheduled run is still active, the loop simply continues. If it finishes within the same `HH:MM` minute, a later 15-second tick can still start the due entry; after the minute passes, the entry is effectively missed for that game day because `already_triggered` is only marked after `_start_run()` succeeds.

## Implementation

- Added `src/linux_maa/run_coordinator.py` with process-local `RunCoordinator`, `RunLease`, `RunResource`, and priority constants.
- Current conflict detector is generic over resources but only implements `adb-device` equality by submitted connection address.
- Priorities:
  - automatic scheduled run: highest
  - manual-triggered scheduled run: middle
  - manual Maa run and tool run: normal
- Conflict behavior:
  - new lower-priority run conflicting with active higher-priority run raises `RunConflictError`, surfaced by existing API handlers as 409.
  - new equal-priority run waits for resource release.
  - new higher-priority run calls the lower-priority run's stop callback and waits; if the owner has a configured stop-kill threshold, the coordinator later calls its force-stop callback through that owner manager.
- Wired a single shared coordinator through `WebServices` into `MaaRunManager`, `SchedulerService`, and `ToolRunManager`.
- Manual Maa runs claim the ADB resource from the submitted profile's `connection.address`, falling back to `DEFAULT_DEVICE_SERIAL` when no address exists.
- Scheduled Maa runs claim the resource from `ScheduleConfig.profile_data.connection.address`; automatic trigger uses highest priority, manual trigger uses middle priority.
- `game-update` tool claims the submitted `address` or default profile address. Maintenance actions currently claim no ADB resource.
- Kept existing one-current-run-per-manager UI/SSE model. This change does not implement multi-device parallel current-run views inside the same manager.
- Updated `README.md`, `docs/maa-runtime.md`, and `docs/architecture-direction.md`.

## Commands

- `rg` searches over `src/linux_maa` for current/run/start/locking terms.
- `nl -ba` reads for `src/linux_maa/maa/runner.py`, `src/linux_maa/scheduler/service.py`, `src/linux_maa/tools/manager.py`, `src/linux_maa/maa/maintenance.py`, route files, and `web/services.py`.
- `uvx ruff check src tests` — passed.
- `uv run python -m compileall -q src tests` — passed.
- `uv run pytest -q` — 57 passed.
- `git diff --check` — passed.
- Restarted `linux-maa-webui.service`; immediate curl was too early while the service was still opening port 8000, then `/api/settings` passed on the next short poll with 2770-byte response.
