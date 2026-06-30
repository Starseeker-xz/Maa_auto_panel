# Session 2026-06-30_0014-task-editor-fixes

## Task

User requested task editor fixes:
- Rename metadata "重要任务" to "非重要任务", place it first, and disable remaining two metadata fields when checked.
- Improve left-pane drag behavior so target location is visible and item movement is understandable.
- Fix malformed/unclickable middle-pane checkbox visual shown in screenshot.
- Remove dotted underline on tooltip trigger, or switch to right-side question icon.
- Add dependency/disable handling for mutually exclusive params such as Infrast `drones` disabled when `mode = 10000`.
- Review integration docs and correct select labels so enums are user-readable instead of raw numeric values.

## Activity

- Session initialized after reading global lessons, memory index, project history, project lessons, and conversation index.

## Update

- User clarified Infrast was only an example. Need review current visual task templates against integration docs for all missed enum labels and conditional ineffective fields.
- User also requested splitting task-type UI templates into separate files.

## Implemented

- Updated metadata UI in `ConfigEditorPane`: top field is now `非重要任务`, mapped to `important = false`; checking it disables the unlimited-run and minimum-daily-success controls.
- Reworked left task-list drag behavior in `TaskListPane`/`MainPage`: handle still starts drag, but the full row is used as the drag image and row gaps show a cyan insertion line.
- Fixed JSON Forms checkbox distortion by excluding checkbox inputs and Radix checkbox internals from broad `.jsonforms-surface input` styling.
- Replaced dotted-underlined tooltip labels with a small `HelpCircle` icon button next to labels.
- Added JSON Forms support for `oneOf` enum titles and schema-local `x-enabledWhen` / `x-disabledWhen` conditions.
- Split visual task editor templates from one `frontend/src/config/task-editor-schemas.json` into per-task files under `frontend/src/config/task-editor-schemas/`.
- Reviewed current visual templates against `docs/maa-upstream/zh-cn/protocol/integration.md` for StartUp, CloseDown, Fight, Recruit, Infrast, Mall, Award.
- Added current conditional UI handling:
  - Fight: `penguin_id` requires `report_to_penguin`, `yituliu_id` requires `report_to_yituliu`; `series` uses titled options.
  - Recruit: `set_time` requires `times = 0`, `expedite_times` requires `expedite = true`, report IDs require corresponding upload toggles, `extra_tags_mode` uses titled options.
  - Infrast: `mode`, `drones`, facilities use titled options; `drones`, `threshold`, `filename`, `plan_index` respect documented mode availability.
  - Mall: `formation_index` requires `credit_fight = true`.
  - Client/server enums now use display titles while preserving original submitted values.

## Tests

- `npm run build` in `frontend/`: passed after adding `frontend/src/vite-env.d.ts`. Vite emitted only the existing large chunk warning.
- Confirmed WebUI service is listening on `0.0.0.0:8000` with process `linux-maa` pid `50435`.

## Notes

- Frontend edits remain local-only; no save/sync-to-disk behavior was added in this session.
- Used a Node script for mechanical JSON migration/splitting after first editing rules in the aggregate JSON.

## Regression Fix

- User reported only metadata change worked; task editor showed all task types as not connected, and left-list spacing/dragging broke.
- Confirmed `frontend/src/lib/taskSchemas.ts` still imported removed `frontend/src/config/task-editor-schemas.json`; fixed by explicit imports of the split per-task JSON files.
- Confirmed drag insertion markers were rendered as independent grid children, which expanded vertical spacing; fixed by rendering insertion lines absolutely inside each row wrapper.
- Moved drag start back to the handle itself while setting the drag image to the full row, making handle drag reliable without stretching row gaps.
- Added `isOneOfEnumControl` to custom JSON Forms renderers so `oneOf` title/value options use the project select renderer.
- Re-ran `npm run build` in `frontend/`: passed; Vite emitted only the large chunk warning.

## Drag Indicator Fix

- User reported no insertion line when dragging to the first position.
- Cause: first-row top insertion line used negative top offset and could be clipped at the scroll viewport/list top.
- Fix: added top padding to the list and render first-position insertion line at `top-0`; other top/bottom lines remain positioned in the inter-row gap.
- Re-ran `npm run build` in `frontend/`: passed; Vite emitted only the large chunk warning.

## Add Buttons

- Added local-only task config creation in the left pane: plus button beside current task config toggles a slide-down panel with name input and confirm button.
- Added local-only subtask creation: lower-left plus opens an upward Select of task types using defaults from `frontend/src/config/task-item-defaults.json` via `frontend/src/lib/taskItemDefaults.ts`.
- Removed the lower plus tooltip; this follows the user's direction to avoid pop/tooltip on such controls by default.
- Aligned the top task-config selector width with task rows by applying matching right padding to the top controls and lower button rows.
- Re-ran `npm run build` in `frontend/`: passed; Vite emitted only the large chunk warning.

## Frontend Audit Before Save Work

- Added hover-only row actions for task items: rename and delete icon buttons, no copy action.
- Connected task-item checkboxes to local state and made `全选` / `清空` functional.
- Moved task workspace pure helpers into `frontend/src/lib/taskWorkspace.ts`: local config response/file construction, config name uniqueness, reindex, rename, delete, enable toggles, and delete-selection helper.
- Made JSON Forms param and Linux MAA metadata edits update the parent task-item state, so edits survive selection changes within the current frontend session.
- Hardened `frontend/src/lib/api.ts` so non-JSON or empty error responses do not mask the original backend status/detail.
- Updated `README.md`, `docs/maa-runtime.md`, and `.codex/project-history.md` to reflect split editor templates, local task defaults, local-only editing state, and the upcoming backend save phase.
- Re-ran `npm run build` in `frontend/`: passed; Vite emitted only the large chunk warning.

## Final Audit Pass

- Added `initialTaskConfig` ref in `MainPage` so initial config-list loading intentionally uses the first routed task without breaking local-created configs on later route changes.
- Verified no current frontend/docs/project-history references to the obsolete active `task-editor-schemas.json` path remain outside historical session notes.
- Verified `http://127.0.0.1:8000/` serves the rebuilt frontend bundle.
- Re-ran `npm run build` in `frontend/`: passed; Vite emitted only the large chunk warning.
