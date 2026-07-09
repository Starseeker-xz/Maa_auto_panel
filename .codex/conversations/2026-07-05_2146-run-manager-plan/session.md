# Session 2026-07-05_2146-run-manager-plan

## Goal

- Audit current run-manager/runtime orchestration code and produce a detailed Chinese refactor plan before implementation.
- User direction: unify WebServices/SSE/status/run manager logic, move priority/resource helpers to globally scoped modules, extract `run_manager/` package, keep run logic domain-agnostic, make callbacks optional, and include log pipeline/templates/raw-line callback support in manager init/runtime concepts.

## Startup

- Read `~/.codex/lessons.md`, `~/.codex/memories/index.md`, `.codex/project-history.md`, `.codex/project-lessons.md`, and `.codex/conversations/index.md`.
- No detailed global memory loaded; current task is project-specific and unrelated to the listed home-lab memory.

## Session Notes

- Implementation is intentionally deferred until user reviews the audit/plan.

## Audit Summary

- Confirmed: duplicated live-run lifecycle code is concentrated in:
  - `src/linux_maa/maa/runner.py` (manual MAA, 565 lines)
  - `src/linux_maa/scheduler/service.py` (schedule service and live scheduled run, 863 lines)
  - `src/linux_maa/tools/manager.py` (tool runs, 507 lines)
  - `src/linux_maa/maa/maintenance.py` (maintenance runs and update inspection, 388 lines)
- Confirmed: common duplicated mechanics include `LiveRun` creation, current-run slot/version/condition, `current_response()`, `wait_for_change()`, stop/force-stop flags and text events, `RunLease` acquire/release, retry creation/seal/persistence, process streaming with shared timeout fields, log append/flush, run finish, retention calls, and SSE-compatible state shape.
- Confirmed: existing shared primitives already support the target shape:
  - `run_executor.py`: `RunTimeouts`, `LiveRun`, `LiveRetry`
  - `process.py`: streaming subprocess with stop/force/timeout/raw-line callbacks
  - `logs/state.py` + `logs/pipeline.py`: source/block visible-log pipeline
  - `run_state.py`: generic run/retry persistence and history by kind
  - `web/sse.py`: generic `{run, retries}` reset/patch stream
- Confirmed: `run_coordinator.py` currently mixes generic coordinator behavior with global priority constants and ADB-specific resource helpers. User wants priority/resource helpers moved to a global single-purpose file and conflict logic injected at framework startup.
- Confirmed: frontend is already close to generic log rendering. `frontend/src/lib/runStream.ts` and `frontend/src/pages/main/LogPane.tsx` consume generic `RunState`; repeated page code is mostly snapshot/SSE connection setup.

## Difference Summary

- Manual MAA:
  - Dynamic retry command per attempt, generated task config per retry, skip previously successful child tasks, `MaaTaskResultCollector` from raw `maa-cli:stderr`, MaaCore log delta capture, generated config path in retry/run summary.
- Scheduled MAA:
  - Same MAA task execution concerns as manual, plus schedule policy, daily stats, trigger records, game-day timezone, restart script before run/before retry, retry buffer wait, schedule-specific timeouts, final `soft_failed` policy.
- Tool:
  - Closest to generic command mode. Build command once from tool config, repeat same command until success/max retries/stop, status from return code, tool stdout/stderr diagnostics/log sources, resource claim for game-update ADB address.
- Maintenance:
  - Single static maa-cli command, max retries currently 1, no resource claim, update-info inspection is not live-run logic and should remain outside generic manager. Stop/force capability exists in subprocess flags but routes do not currently expose it.

## Planned Architecture Notes

- Proposed new package: `src/linux_maa/run_manager/`.
- Proposed global resource file: `src/linux_maa/run_resources.py`.
- Move current `run_executor.py`, `run_coordinator.py`, and likely `run_state.py` into the run manager package as state/coordinator/store modules, updating imports directly instead of adding compatibility re-export modules.
- Generic manager should own live run slot, status/SSE versioning, stop/force-stop, retry persistence, log pipeline creation, process execution wrapper, coordinator acquire/release, and default retry/result framework events.
- Domain wrappers should only prepare run plans and callbacks/drivers. The generic manager must not understand MAA tasks or scheduler policy; `task_ids` and `task_results` stay opaque fields supplied by callbacks.
- Web layer should also be partly unified:
  - Add a generic current-run router helper/factory for `GET /current`, `GET /current/events`, optional `GET /{run_id}`, stop and force-stop endpoints.
  - Start endpoints stay domain-specific because request validation and preparation differ significantly.
  - Existing routes (`runs`, `tools`, `schedules`, `maintenance`) can mount/compose this generic router while keeping their own list/start/config endpoints.
  - SSE registration should be declarative per manager, using the shared `current_response` and `wait_for_change` contract.

## Written Plan

- Created root document `RUN_MANAGER_REFACTOR_PLAN.md`.
- The document is the authoritative implementation plan unless the user edits it before execution.
- Important execution discipline from user and plan:
  - Before any code edit, reread the relevant plan section.
  - Before any code edit, update this session record with the intended phase, files, scope, and expected verification.
  - After each phase, update this session record with files changed, behavior changes, tests, deviations, and next step.
  - If context is compressed, first reread `RUN_MANAGER_REFACTOR_PLAN.md`, this session file, and latest project-history run-manager entries before continuing.

## Verification

- 2026-07-05: `git diff --check` passed after creating the plan document and updating project state records.
- No business code was changed in this planning turn.
- `git status --short` showed an existing modified `.codex/conversations/2026-07-05_1926-inspect-concurrency/session.md`; this session did not edit or revert that file.

## Implementation Phase 0/1 Preparation

- User approved starting implementation.
- Re-read `RUN_MANAGER_REFACTOR_PLAN.md` sections covering:
  - Web router/SSE notes, including user-added notes about `/{kind}/` prefixes and history `kind`.
  - Stage 0 preparation.
  - Stage 1 moving basic modules.
  - Context compression and recording discipline.
- Current intended scope:
  - Stage 0: run baseline backend verification.
  - Stage 1: create `src/linux_maa/run_manager/`, move `run_executor.py`, `run_state.py`, and `run_coordinator.py` into it, add `src/linux_maa/run_resources.py`, update imports, and keep behavior unchanged.
- Explicit non-scope for this phase:
  - Do not implement `GenericRunManager` yet.
  - Do not migrate tool/maintenance/manual/schedule managers yet.
  - Do not change frontend code yet.
  - Do not change Web router shape yet.
- Expected verification:
  - Baseline before edits: `uvx ruff check src tests`, `uv run python -m compileall -q src tests`, `uv run pytest -q`.
  - After Stage 1: same commands plus `git diff --check`.
- Workspace note:
  - `.codex/conversations/2026-07-05_1926-inspect-concurrency/session.md` is already modified and unrelated; do not edit or revert it.

## Implementation Phase 0/1 Results

- Baseline before code edits:
  - `uvx ruff check src tests` passed.
  - `uv run python -m compileall -q src tests` passed.
  - `uv run pytest -q` passed: 57 tests.
- Stage 1 changes completed:
  - Created `src/linux_maa/run_manager/`.
  - Moved `src/linux_maa/run_executor.py` to `src/linux_maa/run_manager/state.py`.
  - Moved `src/linux_maa/run_state.py` to `src/linux_maa/run_manager/store.py`.
  - Moved `src/linux_maa/run_coordinator.py` to `src/linux_maa/run_manager/coordinator.py`.
  - Added `src/linux_maa/run_resources.py` for global priority constants, `RunResource`, ADB resource helpers, and default resource policy/conflict helper.
  - Updated current imports in backend and tests.
  - Kept runtime behavior unchanged; `RunCoordinator` still accepts numeric priority leases for now.
- Stage 1 verification:
  - `uvx ruff check src tests` passed.
  - `uv run python -m compileall -q src tests` passed.
  - `uv run pytest -q` passed: 57 tests.
  - `git diff --check` passed.
  - `rg` found no remaining imports from `linux_maa.run_executor`, `linux_maa.run_state`, or `linux_maa.run_coordinator`.
- Notes:
  - `src/linux_maa/__pycache__/run_*.pyc` files still exist on disk but are not tracked and did not appear in `git status`.
  - `RUN_MANAGER_REFACTOR_PLAN.md` contains user-added notes about route `/{kind}/` prefixes and history `kind`; those are not Stage 1 changes and remain future constraints.

## Implementation Phase 2 Preparation

- Re-read `RUN_MANAGER_REFACTOR_PLAN.md` sections:
  - Stage 2: implement `GenericRunManager` basis.
  - Key risks: locks/callbacks, terminal idempotence, metadata overwrite, retry-local logs, task-result authority.
  - Verification and context compression discipline.
- Current intended scope:
  - Add `src/linux_maa/run_manager/manager.py`.
  - Implement `RunStartPlan`, `RunTextTemplates`, `RunDriver`, `RunContext`, and `GenericRunManager`.
  - Cover current/get/current_response/wait, start transaction, stop/force-stop, retry seal/persist, run finish, and context helpers.
  - Add tests for the generic manager without migrating existing managers.
- Explicit non-scope for this phase:
  - Do not add command driver yet.
  - Do not add generic router yet.
  - Do not migrate tool, maintenance, manual MAA, or scheduler to `GenericRunManager` yet.
  - Do not change frontend.
- Expected verification:
  - `uvx ruff check src tests`
  - `uv run python -m compileall -q src tests`
  - `uv run pytest -q`
  - `git diff --check`

## Implementation Phase 2 Results

- Added `src/linux_maa/run_manager/manager.py`:
  - `RunTextTemplates`
  - `RunStartPlan`
  - `RunDriver` protocol
  - `RunContext`
  - `GenericRunManager`
- Implemented generic live-run basis:
  - current run storage and `current()` / `get()`
  - `current_response()` compatible with existing `{run, retries, stream_version}` SSE shape
  - `wait_for_change()`
  - start transaction with `RunLease` acquire/release, persistent `create_run()`, current-run active rejection, and driver thread startup
  - `stop_current()` / `force_stop_current()` / `stop()` / `force_stop()`
  - `RunContext.begin_retry()`, `append_event()`, `append_log()`, `flush_log()`, `finish_retry()`, `finish_run()`, `mark_updated()`, `set_process()`, `wait_for_stop()`
  - retry seal + `RunStateStore.add_retry()`
  - run finish + `RunStateStore.finish_run()` + retention + coordinator release
- Added `tests/test_run_manager.py`:
  - successful generic driver persists retry/history and releases resources
  - stop-current path writes diagnostic event and finishes stopped
- During testing, fixed a real Stage 2 bug:
  - stop/force-stop originally wrote only visible framework event blocks, not diagnostic JSONL events.
  - `GenericRunManager.stop()` and `force_stop()` now call `_record_framework_event()` before writing visible log state.
- Stage 2 verification:
  - `uvx ruff check src tests` passed.
  - `uv run python -m compileall -q src tests` passed.
  - `uv run pytest -q` passed: 59 tests.
  - `git diff --check` passed.
- Next planned phase:
  - Stage 3: add default command driver and log profile helpers.

## Implementation Phase 3 Preparation

- Re-read `RUN_MANAGER_REFACTOR_PLAN.md` Stage 3 and verification sections.
- Current intended scope:
  - Add `src/linux_maa/run_manager/logs.py`.
  - Add `src/linux_maa/run_manager/command.py`.
  - Extend `RunContext`/`GenericRunManager` with a `run_process()` wrapper around `run_streaming_process()`.
  - Support command execution with retry, stop/force-stop, runtime/no-output/stop timeout pass-through, stream-to-visible-log, diagnostics sink, and raw-line callback pass-through.
  - Add command driver tests for success/log streaming, retry after nonzero return, raw-line callback, stop handling, and runtime timeout.
- Explicit non-scope for this phase:
  - Do not migrate `ToolRunManager` yet.
  - Do not add generic router yet.
  - Do not change Web routes or frontend.
- Expected verification:
  - `uvx ruff check src tests`
  - `uv run python -m compileall -q src tests`
  - `uv run pytest -q`
  - `git diff --check`

## Implementation Phase 3 Results

- Added `src/linux_maa/run_manager/logs.py`:
  - `RunLogProfile`
  - `plain_stream_log_profile()`
  - stream source mapping and optional diagnostic sink support
- Extended `RunContext` / `GenericRunManager`:
  - Added `run_process()` wrapper around `run_streaming_process()`.
  - Streams subprocess output into visible retry logs via `RunLogProfile`.
  - Writes optional diagnostic output through `RunLogProfile`.
  - Passes through raw-line and timeout callbacks.
  - Sets and clears `LiveRun.process`.
  - Flushes retry logs after process exit.
- Added `src/linux_maa/run_manager/command.py`:
  - `CommandSpec`
  - `CommandRunDriver`
  - `CommandRunTextTemplates`
  - default command retry loop with stop/force-stop/timeout handling.
- Added `tests/test_run_manager_command.py`:
  - success + stream diagnostics + raw-line callback
  - retry after nonzero return code
  - stopping a running process
  - runtime timeout event and failed final status
- During testing, fixed a real Stage 3 bug:
  - Writing `retry_next` after `finish_retry()` created a new log-only retry and exhausted retry count.
  - `CommandRunDriver` now writes retry-next event before sealing the failed retry.
- Stage 3 verification:
  - `uvx ruff check src tests` passed.
  - `uv run python -m compileall -q src tests` passed.
  - `uv run pytest -q` passed: 63 tests.
  - `git diff --check` passed.
- Next planned phase:
  - Stage 4: migrate `ToolRunManager` to `GenericRunManager` + `CommandRunDriver`, and use the generic run control router once implemented.

## Implementation Phase 4 Preparation

- Re-read `RUN_MANAGER_REFACTOR_PLAN.md` sections:
  - Web router/SSE unified registration.
  - Tool migration.
  - Stage 4 migration steps.
- Current intended scope:
  - Add `src/linux_maa/run_manager/router.py` for common current/status/SSE/stop/force-stop routes.
  - Keep existing tool API paths unchanged for this migration:
    - `GET /api/tools/current`
    - `GET /api/tools/current/events`
    - `POST /api/tools/current/stop`
    - `POST /api/tools/current/force-stop`
  - Refactor `ToolRunManager` to delegate live lifecycle to `GenericRunManager` + `CommandRunDriver`.
  - Keep tool registry/default config/command builder/resource helper in `tools/manager.py`.
- Explicit non-scope for this phase:
  - Do not migrate maintenance/manual/schedule yet.
  - Do not change frontend.
  - Do not redesign history paths or add `/{kind}` route prefixes yet; user-added plan notes remain future constraints.
- Expected verification:
  - `uvx ruff check src tests`
  - `uv run python -m compileall -q src tests`
  - `uv run pytest -q tests/test_run_coordinator.py tests/test_backend_utilities.py tests/test_run_manager.py tests/test_run_manager_command.py`
  - `uv run pytest -q`
  - `git diff --check`

## Implementation Phase 4 Results

- Added `src/linux_maa/run_manager/router.py`:
  - `RunControlManager` protocol.
  - `RunControlRoutes` options.
  - `register_run_control_routes()` for common `/current`, `/current/events`, current stop/force-stop, optional run-id get/stop/force-stop.
- Refactored `src/linux_maa/tools/manager.py`:
  - `ToolRunManager` now owns `self.runs = GenericRunManager(...)`.
  - `start()` builds a `RunStartPlan` with `CommandRunDriver`.
  - Tool-specific fields kept outside generic manager: registry, default config, command builder, ADB resource helper, default ADB path/address.
  - Tool visible logs use `plain_stream_log_profile("tool", diagnostic_sink=Diagnostics.append_tool_output)`.
  - Tool stop/force-stop text is passed via `RunTextTemplates`.
  - Removed tool-local current slot/version/condition/process/retry/history/log lifecycle code.
- Refactored `src/linux_maa/web/routes/tools.py`:
  - Existing paths are preserved.
  - `/api/tools/current`, `/api/tools/current/events`, `/api/tools/current/stop`, and `/api/tools/current/force-stop` are registered through `register_run_control_routes()`.
- Updated `tests/test_backend_utilities.py`:
  - `test_tool_start_rejects_stopping_current_run` now seeds the delegated `manager.runs` state.
- Stage 4 verification:
  - `uvx ruff check src tests` passed.
  - `uv run python -m compileall -q src tests` passed.
  - `uv run pytest -q tests/test_run_coordinator.py tests/test_backend_utilities.py tests/test_run_manager.py tests/test_run_manager_command.py` passed: 25 tests.
  - `uv run pytest -q` passed: 63 tests.
  - `git diff --check` passed.
- Remaining duplicate route/lifecycle targets:
  - manual run router/manager
  - schedule run router/manager
  - maintenance current/events/manager
- Next planned phase:
  - Stage 5: migrate `MaintenanceActionManager` live run portion to `GenericRunManager` + `CommandRunDriver` and use common router for current/events.

## Implementation Phase 5 Preparation

- Re-read `RUN_MANAGER_REFACTOR_PLAN.md` maintenance migration and Stage 5 sections.
- Current intended scope:
  - Refactor `MaintenanceActionManager` live action execution to `GenericRunManager` + `CommandRunDriver`.
  - Keep `MAINTENANCE_COMMANDS`, `inspect_update_info()`, and version/update helper functions in `maa/maintenance.py`.
  - Use MAA log templates for maintenance command visible logs.
  - Route `/api/maintenance/current` and `/api/maintenance/current/events` through `register_run_control_routes()`.
  - Keep stop/force-stop maintenance endpoints disabled for now.
- Explicit non-scope for this phase:
  - Do not migrate manual MAA or scheduler.
  - Do not expose maintenance stop/force-stop in API/UI.
  - Do not change frontend.
- Expected verification:
  - `uvx ruff check src tests`
  - `uv run python -m compileall -q src tests`
  - `uv run pytest -q`
  - `git diff --check`

## Implementation Phase 5 Continuation After Context Compaction

- Re-read the plan sections for `RunLogProfile`, Web router/SSE unification, maintenance migration, and Stage 5 after context compaction.
- Inspected current `src/linux_maa/maa/maintenance.py`; the manager migration patch had landed and no local thread/process lifecycle remained.
- Remaining intended edits before verification:
  - Register maintenance `/current` and `/current/events` through `register_run_control_routes()`.
  - Keep maintenance stop/force-stop routes unexposed.
  - Tidy `maintenance.py` formatting/imports if ruff reports issues.

## Implementation Phase 5 Results

- Refactored `src/linux_maa/maa/maintenance.py`:
  - `MaintenanceActionManager` now owns `self.runs = GenericRunManager(...)`.
  - Maintenance `start(kind)` now builds a `RunStartPlan(kind="maintenance")` with `CommandRunDriver` and a fixed maa-cli command from `MAINTENANCE_COMMANDS`.
  - MAA visible log templates are provided through a local `RunLogProfile`; raw maa-cli output still goes through `Diagnostics.append_maa_cli_output`.
  - Version/update inspection helpers remain local and outside live-run lifecycle.
  - Removed local thread/condition/current/process/retry/log lifecycle code from maintenance manager.
- Refactored `src/linux_maa/web/routes/maintenance.py`:
  - `/api/maintenance/current` and `/api/maintenance/current/events` are now registered through `register_run_control_routes()`.
  - Maintenance stop/force-stop routes remain unexposed.
- Stage 5 verification:
  - `uvx ruff check src tests` passed.
  - `uv run python -m compileall -q src tests` passed.
  - `uv run pytest -q` passed: 63 tests.
  - `git diff --check` passed.
- Remaining duplicate lifecycle targets:
  - manual MAA run manager/router
  - scheduler live-run portion and routes

## Implementation Phase 6 Preparation

- Re-read `RUN_MANAGER_REFACTOR_PLAN.md` sections:
  - Manual MAA difference audit.
  - `ManualMaaRunDriver` target flow.
  - Stage 6 migration checklist.
  - Key risks around callback locking, retry-local logs, task result authority, generated config dir, MaaCore log capture, and stop/force-stop idempotence.
- Inspected current `src/linux_maa/maa/runner.py`, `src/linux_maa/run_manager/manager.py`, `src/linux_maa/run_manager/logs.py`, `src/linux_maa/web/routes/runs.py`, and related references.
- Current intended scope:
  - Refactor `MaaRunManager` to own `self.runs = GenericRunManager(...)`.
  - Extract manual-specific run loop into `ManualMaaRunDriver` inside `maa/runner.py`.
  - Keep `MaaRunRequest`, task file helpers, generated config helpers, task policy helpers, and `_profile_data()` in the manual domain module.
  - Use `RunContext.run_process()` with an MAA `RunLogProfile` so visible logs, diagnostics, raw-line callbacks, process handle, and timeout callbacks flow through the generic manager.
  - Register `/api/runs/current`, `/api/runs/current/events`, `GET /api/runs/{run_id}`, and run-id stop/force-stop through the common router.
- Explicit non-scope for this phase:
  - Do not migrate scheduler live-run behavior yet.
  - Do not change frontend.
  - Do not change MAA task-result parsing semantics.
  - Do not redesign history kind/category paths yet.
- Expected verification:
  - `uvx ruff check src tests`
  - `uv run python -m compileall -q src tests`
  - targeted backend tests if added/affected
  - `uv run pytest -q`
  - `git diff --check`

## Implementation Phase 6 Results

- Refactored `src/linux_maa/maa/runner.py`:
  - `MaaRunManager` now owns `self.runs = GenericRunManager(...)`.
  - Added `ManualMaaRunDriver` for manual MAA retry semantics: task config load, policy parsing, enabled task selection, generated config per retry, raw stderr `MaaTaskResultCollector`, MaaCore log delta capture, retry-only unfinished task selection, final summary.
  - Manual visible logs use an MAA `RunLogProfile` and `RunContext.run_process()`, so diagnostic output, visible log streaming, process handle, stop/force-stop, timeout events, and raw-line callback pass through generic manager infrastructure.
  - Manual stop/force-stop text now comes from `RunTextTemplates`.
  - Removed manual manager local thread/current/version/condition/process/log/retry/run finish lifecycle code.
- Refactored `src/linux_maa/web/routes/runs.py`:
  - Start endpoint remains manual-specific.
  - `/api/runs/current`, `/api/runs/current/events`, `GET /api/runs/{run_id}`, `POST /api/runs/{run_id}/stop`, and `POST /api/runs/{run_id}/force-stop` are now registered through `register_run_control_routes()`.
- Added `tests/test_manual_run_manager.py`:
  - Covers disabled-task manual run skip path.
  - Confirms skipped run persists exactly one sealed retry.
- During migration, fixed the same retry-log hazard seen in Stage 3:
  - Manual “准备重试” and “重试次数已达上限” events must be written before `finish_retry()`, otherwise generic append-event creates a new log-only retry after the previous retry is sealed.
- Stage 6 verification:
  - `uvx ruff check src tests` passed.
  - `uv run python -m compileall -q src tests` passed.
  - `uv run pytest -q tests/test_manual_run_manager.py tests/test_run_manager.py tests/test_run_manager_command.py tests/test_backend_utilities.py` passed: 20 tests.
  - `uv run pytest -q` passed: 64 tests.
  - `git diff --check` passed.
  - `rg` found no remaining local lifecycle helpers/imports in `src/linux_maa/maa/runner.py` or `src/linux_maa/web/routes/runs.py`.
- Remaining duplicate lifecycle target:
  - scheduler live-run portion and schedule routes.

## Implementation Phase 7 Preparation

- Re-read `RUN_MANAGER_REFACTOR_PLAN.md` sections:
  - Scheduler migration target.
  - Stage 7 checklist.
  - Risks around retry-local logs, schedule stats, task result authority, timeout source, and terminal stop/force-stop idempotence.
- Inspected current `src/linux_maa/scheduler/service.py`, `src/linux_maa/web/routes/schedules.py`, scheduler policy/status tests, and backend utility tests.
- Current intended scope:
  - Refactor `SchedulerService` to own `self.runs = GenericRunManager(...)`.
  - Extract live scheduled-run execution into `ScheduledMaaRunDriver` inside `scheduler/service.py` for now.
  - Keep schedule CRUD, background loop, due-entry detection, schedule response, and daily stats storage in scheduler domain.
  - Move current/current_response/wait/stop/force-stop to delegation over generic manager while preserving `current_response(schedule_id=...)` filtering.
  - Start/due trigger should construct a `RunStartPlan(kind="schedule")` with schedule-specific timeouts, priority name, resource locks, selected task ids, and log buffer factory.
  - Route `/api/schedules/current...` through `register_run_control_routes()`.
- Explicit non-scope for this phase:
  - Do not split scheduler into multiple files unless needed to keep tests passing.
  - Do not change frontend.
  - Do not redesign history kind/category paths.
  - Do not change scheduler policy semantics.
- Expected verification:
  - `uvx ruff check src tests`
  - `uv run python -m compileall -q src tests`
  - scheduler policy/status/backend targeted tests
  - `uv run pytest -q`
  - `git diff --check`

## Implementation Phase 7 Results

- Refactored `src/linux_maa/scheduler/service.py`:
  - `SchedulerService` now owns `self.runs = GenericRunManager(...)`.
  - Added `ScheduledMaaRunDriver` for scheduled MAA live-run semantics: initial selected/skipped task handling, restart scripts, retry buffer wait, Maa task execution, raw stderr `MaaTaskResultCollector`, MaaCore log delta capture, daily stats update, retry policy, and `_final_status()`.
  - `SchedulerService` keeps schedule CRUD, background loop, due-entry detection, schedule response, schedule config access, `ScheduleScriptManager`, and daily stats store access.
  - `_start_run()` now computes task data, game day, sorted entries, task policies, initial selection, resources, priority, log files, and creates `RunStartPlan(kind="schedule")`.
  - `current()`, `current_response()`, `wait_for_change()`, `stop_current()`, and `force_stop_current()` now delegate to generic manager; `current_response(schedule_id=...)` still filters snapshots for per-schedule detail pages.
  - Removed scheduler-local current slot/version/condition/process/log append/retry seal/run finish lifecycle helpers.
- Refactored `src/linux_maa/web/routes/schedules.py`:
  - Schedule CRUD and start-now endpoint remain schedule-specific.
  - `/api/schedules/current`, `/api/schedules/current/events`, `/api/schedules/current/stop`, and `/api/schedules/current/force-stop` are registered through `register_run_control_routes()`.
- Updated tests:
  - Existing restart-script visible-log/diagnostics test now exercises `ScheduledMaaRunDriver` through `GenericRunManager`.
  - Existing terminal force-stop service test now checks delegation to `runs`.
  - Added `tests/test_scheduler_run_manager.py` to confirm scheduled skip persists exactly one sealed retry.
- Stage 7 verification:
  - `uvx ruff check src tests` passed.
  - `uv run python -m compileall -q src tests` passed.
  - `uv run pytest -q tests/test_scheduler_policy.py tests/test_scheduler_service_status.py tests/test_backend_utilities.py` passed: 22 tests.
  - `uv run pytest -q` passed: 65 tests.
  - `git diff --check` passed.
  - `rg` confirmed old scheduler-local lifecycle symbols are gone; remaining `RunLease`/`run_streaming_process` references are in generic manager/coordinator/process tests only.
- Post-record cleanup:
  - Removed unused `ScheduledMaaRunDriver.task_data`, `ScheduledMaaRunDriver.game_day`, and old `_new_schedule_log_buffer()`.
  - Re-ran `uvx ruff check src tests`, `uv run python -m compileall -q src tests`, `uv run pytest -q` (65 passed), and `git diff --check`; all passed.
- Final consistency edit planned:
  - Inject shared `RunCoordinator` into `MaintenanceActionManager` from `WebServices`, matching tool/manual/scheduler construction.
  - Maintenance still declares no resources and exposes no stop routes; this only aligns framework wiring.
- Final consistency edit results:
  - `MaintenanceActionManager` now accepts optional `run_coordinator`.
  - `create_services()` passes the shared `run_coordinator` to maintenance, so all four run domains use the same framework-level coordinator instance.
  - Re-ran `uvx ruff check src tests`, `uv run python -m compileall -q src tests`, `uv run pytest -q` (65 passed), and `git diff --check`; all passed.
- Remaining planned work:
  - Optional frontend stream hook cleanup.
  - Optional post-refactor documentation/architecture notes.
  - Optional route/history `{kind}` prefix/category follow-up from user edits in the plan.
