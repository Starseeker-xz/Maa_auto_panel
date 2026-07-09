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

## Next-Session Refactor Audit

User requested a handoff plan for reducing per-run manager duplication and making `RunCoordinator` a strict backend-global property.

### Confirmed duplication

- `MaaRunManager`, `ToolRunManager`, `SchedulerService` run half, and `MaintenanceActionManager` each own the same lifecycle skeleton:
  - `runtime` / `run_state` / `diagnostics` / `framework_settings` deps
  - lock, condition, stream version, current run lookup/response, SSE wait
  - `LiveRun` construction, `RunStateStore.create_run()`, thread startup, current assignment
  - stop / force-stop methods and coordinator stop callbacks
  - `LiveRetry` creation, log flushing, retry sealing, `RunStateStore.add_retry()`
  - `RunStateStore.finish_run()`, retention enforcement, `RunCoordinator.release()`
  - process wiring around `run_streaming_process()`, timeout event text, `state.process` updates
- Current duplication is not just cosmetic; it caused divergent behavior:
  - manual formerly only blocked `running`, tool blocked `running|stopping`, maintenance still blocks only `running`
  - scheduled current is `_current`, manual/tool use `_runs + _current_run_id`
  - framework event formatting and diagnostics output differ slightly across managers
  - coordinator acquire/release error paths are repeated in three start/finish paths

### Confirmed differences to preserve

- Manual Maa run:
  - input is `MaaRunRequest`
  - ADB resource from selected profile
  - retry selection skips already successful task ids
  - uses `MaaTaskResultCollector`
  - generated task config under `runtime/maa/generated-configs/<run-id>`
  - captures MaaCore log delta per retry
- Scheduled run:
  - `SchedulerService` also owns schedule CRUD/list/status/timeline/daily stats/background due-entry loop
  - single run input is `(ScheduleConfig, ScheduleEntry, trigger, retry_count)`
  - ADB resource from schedule `profile_data`
  - automatic trigger priority differs from manual schedule trigger priority
  - task selection and final status depend on daily stats, remaining slots, important/unlimited policies
  - restart scripts can run before run and before retry, and their output belongs to the active retry
  - scheduled timeouts come from schedule config, not framework settings
- Tool run:
  - input is `(tool_id, config, retry_count)`
  - tool registry builds command/env
  - current only `game-update` claims ADB resource
  - success/failure is return-code based
- Maintenance action:
  - input is maintenance kind
  - no ADB resource currently
  - single retry
  - also has update-info inspection APIs that should stay out of the generic run manager

### Proposed architecture

- Add a generic lifecycle module, likely `src/linux_maa/run_manager.py`.
- Keep `run_executor.py` focused on `LiveRun`, `LiveRetry`, timeout data, and common dataclasses. Do not bury manager/service logic there unless the file is renamed or split; it is currently a state model module, not a service module.
- Introduce a generic `RunManagerBase` (or concrete `LiveRunManager`) that owns:
  - lock/condition/version/current storage
  - `current()`, `current_response()`, `wait_for_change()`, `get(run_id)`
  - start transaction: build plan, acquire coordinator, create persisted run, set current, start thread, release on startup failure
  - stop and force-stop by current or run id
  - coordinator stop callback creation
  - `append_framework_event()`, stream log append, flush, `mark_log_updated()`
  - `begin_retry()`, `finish_retry()`, `finish_run()`
  - generic `run_process()` wrapper around `run_streaming_process()`
- Use hooks/protocols for domain-specific behavior. Suggested minimal hook shape:
  - `prepare_start(request, run_id) -> RunStartPlan`
    - returns kind, title, priority, resources, max_retries, log files, event log file, live metadata, persisted metadata, selected task ids, optional force-after seconds
  - `execute(context, request, state) -> RunCompletion`
    - owns domain retry policy and calls context helpers to begin/seal retries, append logs, and run processes
  - optional `format_stop_message`, `format_force_stop_message`, `timeout_message(level, elapsed)`
  - optional `should_accept_new_current(current)` if a domain ever needs non-default same-manager behavior
- `RunContext` should wrap shared helpers and hide raw manager internals:
  - `begin_retry(task_ids=..., retry_group=..., log=..., log_files=...)`
  - `append_event(text, tone=...)`
  - `append_stream(source_kind, stream, text)`
  - `flush_retry_log(retry)`
  - `run_process(cmd, env, retry, timeouts, on_raw_line=None, output_source_prefix=...)`
  - `finish_retry(...)`
  - `finish_run(...)`
  - `notify()`

### Proposed file split

- `src/linux_maa/run_coordinator.py`
  - keep resources/priorities/conflict logic
  - add `GLOBAL_RUN_COORDINATOR = RunCoordinator()` and `global_run_coordinator()`
- `src/linux_maa/run_manager.py`
  - new generic manager, start plan/result/context/protocols
- `src/linux_maa/maa/runner.py`
  - shrink to `MaaRunDriver` / hook implementation plus existing config generation helpers
  - export a small facade if routes still expect `MaaRunManager`
- `src/linux_maa/tools/manager.py`
  - keep tool registry and command builders
  - delegate lifecycle to generic manager with `ToolRunDriver`
- `src/linux_maa/maa/maintenance.py`
  - keep update-info inspection helpers
  - delegate maintenance action process execution to generic manager/driver
- `src/linux_maa/scheduler/service.py`
  - keep schedule CRUD/timeline/background loop/daily policy
  - replace `_start_run`, stop/current lifecycle, retry/log/process boilerplate with a schedule-run driver owned by the generic manager
  - `current_response(schedule_id=...)` can filter generic current by `metadata["schedule_id"]`

### RunCoordinator global plan

- Current state: `WebServices.create_services()` constructs a coordinator and injects it into managers. Individual managers also create a fresh `RunCoordinator()` if none is passed, which makes accidental non-shared managers easy.
- Desired state: `RunCoordinator` is process-global by default and not a Web layer dependency.
- Implementation:
  - in `run_coordinator.py`, define one module-level singleton
  - manager constructors default to that singleton via `global_run_coordinator()` or a class-level `default_coordinator`
  - keep optional injection only for tests and explicit isolated unit use
  - remove `run_coordinator` from `WebServices` dataclass unless there is an API endpoint that explicitly reports occupied resources
  - route/service creation should not decide global resource scope

### Suggested migration order

1. Add global coordinator singleton and change existing constructors to use it by default. Update tests that expect isolation to pass an explicit fresh coordinator.
2. Add `RunManagerBase` and port `ToolRunManager` first. It is the smallest domain: command builder + return-code retry.
3. Port `MaintenanceActionManager` next. It validates that single-retry, no-resource runs fit the generic lifecycle while keeping update-info methods local.
4. Port manual Maa runs. Reuse `MaaTaskResultCollector`, generated config, retry unfinished policy, and MaaCore log capture through context hooks.
5. Port scheduled runs last. Keep `SchedulerService` as schedule domain service; introduce a contained `ScheduleRunDriver` for one live scheduled run.
6. After each port, run focused tests and add regression tests for:
   - current response/SSE version changes
   - stop and force-stop idempotence
   - coordinator acquire/release on success, startup failure, and execution exception
   - persisted retry/history shape unchanged
   - task result collector remains authoritative for manual/scheduled

### Risks and constraints

- Do not let coordinator callbacks run while manager locks are held. Current coordinator correctly calls callbacks outside its own lock; keep that property.
- Preserve `{run, retries}` live/history payload shape.
- Preserve retry-local visible log buffers and task-results separation.
- Preserve scheduled daily stats and final-status policy exactly; only lifecycle plumbing should move.
- Equal-priority conflict waits can block the caller thread. That is current requested behavior; do not silently convert it to queueing unless the user asks.
- A future multi-device parallel model would require changing each page's single-current-run UI/SSE contract. This refactor should not accidentally introduce multi-current state.
