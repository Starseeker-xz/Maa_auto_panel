# Session 2026-07-02_1933-config-sync-ui-schema

## Task

- User asked how frontend/backend task config synchronization currently works, and whether deprecated UI fields can simply be deleted from `frontend/src/config/task-editor-schemas` without causing missing behavior, warnings, or dead code.

## Notes

- No business code changes.
- Confirmed current config sync path:
  - Backend `GET /api/configs/tasks/{name}` returns parsed `data`, editable `task_items`, validation, and metadata schema.
  - Frontend `MainPage` stores local task item drafts; `ConfigEditorPane` edits `params` with JSON Forms and `linux_maa` metadata separately.
  - Save sends `{ data, task_items }` to `PUT /api/configs/tasks/{name}`.
  - Backend converts task items back to maa-cli config with `task_items_to_config_data()`, validates, and writes TOML/JSON.
- Confirmed `frontend/src/config/task-editor-schemas/*.json` is frontend-only visual/editor schema. Backend validation does not import it.
- Current deprecated visual fields found:
  - `Fight.expiring_medicine`
  - `Recruit.skip_robot`
- Removing a deprecated field only from `advanced` hides it from UI while preserving existing values in `params`.
- Removing the schema property too is build-safe if the UI key is also removed, because templates allow `additionalProperties` and backend maa-cli task schema accepts arbitrary task param keys matching `[a-zA-Z0-9_]+`.
- Removing only the property while leaving it in `general`/`advanced` leaves a dangling JSON Forms control scope and may render a strange fallback control; avoid this.
- Hiding these fields will not automatically delete old values from saved configs. Existing old params can round-trip through drafts and saves unless a cleanup/migration is added.

## 2026-07-02 Follow-up

- User asked to re-check and rebuild after UI schema cleanup, and asked how tooltip descriptions work.
- Checks run:
  - `rg -n "task-editor-schemas|taskSchemas|schemaForTaskType" src/linux_maa frontend/src -g '!frontend/node_modules/**'`
    - Confirmed no backend references; only frontend `taskSchemas.ts` and `ConfigEditorPane.tsx` use task editor templates.
  - `rg -n "expiring_medicine|skip_robot|deprecated" frontend/src/config/task-editor-schemas frontend/src/lib frontend/src/pages/main`
    - No matches; deprecated frontend task editor fields had no remaining references in that chain.
  - `cd frontend && npm run build`
    - Passed. Vite still emitted the known large chunk warning (`index-*.js` around 752 kB minified / 240 kB gzip).
- Tooltip logic:
  - `jsonformsRenderers.tsx` reads `schema.description` when it is a string.
  - `FieldLabel` renders `HelpTooltip` only when description/help is truthy.
  - Removing a field's `description` from the task editor JSON removes that field's tooltip without affecting backend config validation.

## 2026-07-02 Schedule stats refresh

- User asked to update `http://192.168.5.15:8000/schedule/daily-test` schedule detail stats so the center "统计" tab refreshes once after a scheduled run completes.
- Implemented frontend-only change in `frontend/src/pages/SchedulePage.tsx`.
- Previous behavior:
  - `ScheduleStats` used `detail.daily_stats` and `detail.recent_runs`.
  - `detail` was refreshed on route load/save/reset but not when the SSE run stream finished.
- New behavior:
  - Tracks previous `globalRun` in a ref.
  - When a scheduled run transitions from `running`/`stopping` to a non-active state, refreshes `listSchedules()` and, for the visible schedule, calls `readSchedule()`.
  - Merges only runtime/detail fields (`file`, `task_config`, `task_policies`, `timeline`, `daily_stats`, `recent_runs`, `scripts`, `current_run`) into `detail`; it intentionally does not overwrite `detail.config`, `draft`, or `draftTaskConfig`, so unsaved edits are not discarded by a post-run refresh.
  - Centralized start-button disabled reason in `scheduleStartDisabledReason()`.
  - Added `runBusy` so start/stop requests cannot be double-submitted.
  - Start is now disabled while dirty, because the backend runs the saved schedule from disk and would not use unsaved visible draft changes.
- Verification:
  - `cd frontend && npm run build` passed with only the existing Vite large chunk warning.
  - `systemctl is-active linux-maa-webui` reported `active`.
  - `ss -H -ltn sport = :8000` showed `0.0.0.0:8000` listening.
  - `curl -fsS http://127.0.0.1:8000/schedule/daily-test` served the new built asset `/assets/index-X-BN5FN3.js`.

## 2026-07-02 Log details button and summary diagnosis

- User asked to move log path/details out of the log header into a small lower-left `i` button, include preprocessing choices, remove the old visible `info`, and only inspect why the latest scheduled run summary did not naturally form one block.
- Implemented frontend-only change in `frontend/src/pages/main/LogPane.tsx`.
- New LogPane behavior:
  - Header now shows only title and status pill.
  - A lower-left `i` button toggles a small details panel.
  - Details panel includes run id, schedule name, entry name, `log_files` paths, legacy `log_file` fallback, and preprocessing messages matching `选择战斗关卡:` / `选择基建计划:` from normalized log entries.
  - The previous header-side literal `info` and always-visible log paths were removed.
- Verification:
  - `cd frontend && npm run build` passed with only the existing Vite large chunk warning.
  - `curl -fsS http://127.0.0.1:8000/schedule/daily-test` served new asset `/assets/index-CXQ_eVgV.js`.
  - Playwright opened `http://127.0.0.1:8000/schedule/daily-test`, clicked `本次运行详情`, confirmed one details panel and no exact `info` text in `header`.
- Summary diagnosis only, no backend fix yet:
  - Latest scheduled run examined: `2b1fbfec1038`.
  - Raw stdout has `Summary` and the summary body in `debug/linux-maa/external/maa-cli/2b1fbfec1038.stdout.log`.
  - Raw stderr has timestamped `[... INFO ] AllTasksCompleted` at the end in `debug/linux-maa/external/maa-cli/2b1fbfec1038.stderr.log`.
  - Current translator starts a summary block on the unprefixed stdout `Summary`, but clears `_current_summary` whenever a later parsed line has a timestamp.
  - Because the merged live stream can deliver stderr `AllTasksCompleted` between stdout `Summary` and the later stdout summary body, the summary block is closed early and following stdout summary body lines render as ordinary line cards.
  - Reproduced with `MaaCliLogTranslator` by feeding `Summary\n`, then timestamped `AllTasksCompleted\n`, then summary tail lines; resulting entries were one empty summary plus separate line entries.

## 2026-07-02 Source-aware log grouping design notes

- User asked whether a more precise source-tagged translator scheme would work and what the concrete backend logging/reconnect flow would be.
- Current backend flow:
  - `run_maa_cli_process()` already identifies each pipe as `stdout` or `stderr` while reading with `select`.
  - Manual/scheduled `_append_maa_log()` persists raw text to source-specific diagnostics through `Diagnostics.append_maa_cli_output(run_id, stream, text)`.
  - The same `_append_maa_log()` then calls `state.log_translator.translate(text)` without passing `stream`, so `MaaCliLogTranslator` currently has one `_partial`, one `_current`, and one `_current_summary` shared by both sources.
  - Any translated text is appended to `state.lines`; structured UI entries come from `state.log_translator.entries()` in current-run snapshots.
- Proposed precise scheme:
  - Change translator entrypoints to accept `source` for process output, likely `translate(text, source="stdout"|"stderr")` and `flush(source=None)` or flush-all.
  - Keep line-buffer and block state per source where stream interleaving is harmful, at minimum `_partial_by_source`, `_current_summary_by_source`, and possibly `_current_by_source`.
  - Preserve one combined `log_entries` list for UI, but make source-specific blocks update their existing record instead of being closed by another source's timestamped line.
  - This fixes stdout `Summary` being interrupted by stderr `AllTasksCompleted`; it does not reorder delayed stdout hot-update git output back to the beginning.
- SSE/reconnect concern:
  - Online SSE already supports old-entry updates because `build_state_patch()` computes the first differing index and sends `{replace_from, items}`; frontend `applyArrayPatch()` accepts any `replace_from`.
  - Reconnect currently uses cursors by array length. `build_cursor_patch()` only rewinds mutable tail fields by one item, so if a source-aware translator allows older entries to mutate while the client is disconnected, a reconnect may miss that older update.
  - Robust reconnect options: resend full `log_entries` on cursor recovery (`replace_from: 0`, acceptable with the current 1000-entry cap), or maintain per-run earliest dirty index/revision and use that instead of length-only cursors.

## 2026-07-02 Source-aware log grouping implementation

- Implemented backend changes:
  - `MaaCliLogTranslator.translate()` now accepts `source`; scheduler/manual `_append_maa_log()` pass stdout/stderr through.
  - Translator state is now source-aware for partial line buffers, current task, current summary, current git-output block, and task elapsed timing.
  - SSE `build_cursor_patch()` now always includes full `log_entries` (`replace_from: 0`) when cursor recovery is needed; online `build_state_patch()` remains first-difference based.
  - Added `资源拉取结果` grouping for source-local git output starting with `From https://github.com/`, `Updating <rev>..<rev>`, or `Already up to date.`.
  - Added log translations for current sanity, mission started/sanity use, drops/furni, recruit result/tag status, ProductChanged, ProductOfFacility products, EnterFacility facilities, CustomInfrastRoomOperators, base-shift summary `... with operators`, and summary recruit/drops lines.
- User clarified stderr has no summary, so git-output grouping does not need special stderr-summary handling. Implementation still keeps a small stdout guard so `Already up to date.` does not get appended to a previous stdout summary.
- Tests run:
  - `uv run python -m compileall -q src tests`: passed.
  - `uv run pytest tests/test_maa_logs.py tests/test_web_sse.py -q`: 16 passed.
  - `uv run pytest -q`: 38 passed.
  - Real-sample replay with run `2b1fbfec1038`: first summary held 6 messages, later `Already up to date.` became a `资源拉取结果` block, second summary held 21 messages.
- Environment effect:
  - Restarted `linux-maa-webui` systemd service to apply backend code. Service is active, listening on `0.0.0.0:8000`, and `GET http://127.0.0.1:8000/api/schedules/current` returned `{"status":"idle","output":[],"stream_version":0}`.
- Color ownership finding:
  - Backend owns semantic `tone` and optional per-message `segments` in `MaaLogMessage`.
  - Frontend `frontend/src/pages/main/LogPane.tsx` owns actual color classes via `TASK_STATUS_CLASS`, `TASK_PANEL_CLASS`, and `MESSAGE_TONE_CLASS`; `MessageContent` applies segment-level tone/strong styling.
