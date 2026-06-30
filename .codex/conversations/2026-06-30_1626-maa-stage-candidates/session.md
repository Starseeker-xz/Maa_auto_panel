# Session 2026-06-30_1626-maa-stage-candidates

## Notes

- Started session to replicate MAA GUI currently-available Fight stage candidate logic in backend.
- Read project history and confirmed prior finding: MAA GUI Fight candidates are GUI-layer `StagePlan` data, not MaaCore schema params.
- Read MAA WPF source from `.codex/conversations/2026-06-29_2232-config-editing/scratch/maa-src`, especially `StageManager.cs`, `StageInfo.cs`, `StageActivityInfo.cs`, and `FightSettingsUserControlModel.cs`.
- User narrowed scope: implement only the currently open/candidate stage list for now; do not wire StagePlan resolution into task serialization.
- Added `src/linux_maa/maa/stages.py` with `MaaStageService.stage_candidates()`.
- Added `GET /api/maa/stages` in `src/linux_maa/web/app.py`. Query params: `client`, `include_unavailable`.
- Validation run:
  - `uv run python -m compileall -q src/linux_maa`: passed.
  - Direct service check: `Official` and `Bilibili` both effective `Official`, current open count 18, no errors; `YoStarJP` current open count 16, no errors.
  - App route check confirmed `/api/maa/stages` registered for GET.
- User asked whether server was running; no process was listening on 8000. Started WebUI with `uv run linux-maa webui --host 0.0.0.0 --port 8000`, uvicorn PID 43010, exec session 39245.
- HTTP check:
  - `GET /api/maa/stages?client=Bilibili`: effective `Official`, 18 stages, no errors.
  - `GET /api/maa/stages?client=YoStarJP`: effective `YoStarJP`, 16 stages, no errors; includes open activity stages `ME-8`, `ME-7`, `ME-6`, `ME-5`.
- User expanded scope to managed middle-editor config:
  - All managed UI configs are saved as runtime placeholders in `tasks.params`.
  - True UI/runtime state is stored under `linux_maa.managed_params`.
  - Generic managed arrays store ordered `{value, enabled}` rows and resolve only enabled rows at run time.
  - Fight `stage` is now a managed candidate array; the runner resolves the first currently open candidate before invoking `maa-cli`.
  - Infrast `plan_index` is now a managed runtime value; the runner can resolve the auto placeholder by reading the selected custom schedule JSON `period` entries.
- Added backend Infrast option service and APIs:
  - `GET /api/maa/infrast/files` lists `config/maa/infrast/*.json` plus the empty "不选择自定义排班文件" option.
  - `GET /api/maa/infrast/plans?filename=...` returns a first time-rotation auto option and one option per schedule plan.
- Updated frontend JSON Forms renderer:
  - `x-linuxMaaManaged` controls whether arrays get enable checkboxes.
  - Ordinary arrays no longer get checkboxes.
  - `x-optionsSource` loads dynamic select/array options from `ConfigEditorPane`.
  - Empty select option values are internally encoded so Radix Select can render Fight "当前/上次" and Infrast "不选择自定义排班文件".
- Infrast `filename` and `plan_index` moved to the general settings tab. Both render as dropdowns. `plan_index` is disabled when `filename == ""`, and descriptions mention that the plan selection is invalid without a custom schedule file.
- Verification:
  - `uv run python -m compileall -q src/linux_maa`: passed after backend changes.
  - `npm run build`: passed after frontend changes.
  - Dataflow script confirmed edit view -> saved placeholders -> runtime projection:
    - Infrast saves `facility = "__linux_maa_runtime__:array:facility"` and `plan_index = "__linux_maa_runtime__:infrast_plan_index"`, then resolves runtime `plan_index = 3`.
    - Fight saves `stage = "__linux_maa_runtime__:fight_stage"`, then resolves runtime `stage = "1-7"`.
    - Mall/Recruit managed arrays save `__linux_maa_runtime__:array:<key>` and restore enabled values.
  - HTTP check after restart: `/api/maa/infrast/files` returns `[{value: "", label: "不选择自定义排班文件"}, {value: "排班.json", label: "搓玉 (排班.json)"}]`.
  - Playwright checked Infrast editor: file dropdown includes "不选择自定义排班文件"; selecting it disables the plan dropdown with no console/page errors. Screenshot: `scratch/infrast-empty-file-disabled.png`.
  - Playwright checked Fight editor: stage option dropdown opens with "当前/上次", "1-7", "R8-11", etc., with no console/page errors. Screenshot: `scratch/fight-stage-options.png`.
- User clarified that Fight "当前/上次" must be a real framework-level value, not an empty string, so it can be selected and used as a fallback even though maa-cli receives an empty `stage`.
- Implemented `CURRENT_STAGE_VALUE = "__linux_maa_stage__:current_last"` in `MaaStageService`.
  - `/api/maa/stages` now returns `value = "__linux_maa_stage__:current_last"` and `maa_value = ""` for "当前/上次".
  - `resolve_first_open_stage()` accepts both the new sentinel and old empty values, but returns `""` to maa-cli.
  - Fight managed metadata normalizes old empty values to the new sentinel on read/project.
- Validation for the sentinel change:
  - Python check confirmed API first stage is `当前/上次`, value sentinel, `maa_value = ""`.
  - Python check confirmed `resolve_first_open_stage([CURRENT_STAGE_VALUE]) == ""` and old `[""]` also resolves to `""`.
  - Python projection check confirmed save metadata stores `__linux_maa_stage__:current_last`, while runtime generated config writes `stage = ""`.
  - Playwright checked Fight editor with current item id `fight-e6d4bc5d`: selecting "当前/上次" from the stage plan dropdown adds a second row instead of only closing the dropdown. Screenshot: `scratch/fight-current-last-selected.png`.
- Migrated existing writable task configs through `ConfigManager.write_task_config()` so disk files also use the new placeholder form. Processed `config/maa/tasks/test.toml`, `startup-smoke.toml`, and `full-current.toml`.
- Post-migration validation:
  - `validate_task_config()` returned valid for `test`, `startup-smoke`, and `full-current`.
  - Re-reading migrated `test.toml` confirmed UI inflation gives Fight `stage = ["1-7"]` and Infrast `plan_index = "3"`.
  - Runtime projection from migrated `test.toml` confirmed Fight `stage = "1-7"` and Infrast `plan_index = 3`, with no skip messages.
- Mistakes during verification:
  - A quick Python projection script had an invalid dict-comprehension expression; fixed and reran.
  - A second projection script used old `ConfigManager` construction/method names; corrected to `ConfigManager(MaaRuntime(...))` and `read_task_config()`.

## Active Environment Effects

- Old WebUI process in exec session 39245 / uvicorn PID 43010 was stopped earlier in the session.
- WebUI process in exec session 56045 / uvicorn PID 12025 was stopped to load backend changes.
- WebUI process in exec session 74277 / uvicorn PID 21664 was stopped to load the Fight "当前/上次" sentinel change.
- WebUI is currently running on `http://0.0.0.0:8000` from exec session 32056 / uvicorn PID 30808.

## Implementation Notes

- GUI maps `Bilibili` to `Official` in `StageManager.GetClientType()`, so backend does the same.
- GUI activity times in `StageActivityV2.json` are parsed as local-to-the-entry timezone then converted to UTC by subtracting `TimeZone`; backend mirrors that.
- GUI resource/permanent stage weekly schedules use .NET Monday=1 style conceptually; backend uses Python `datetime.weekday()` values where Monday=0. The hardcoded schedules were translated accordingly.
- Fight candidate list building is in `MaaStageService.stage_candidates()`. Runtime Fight stage plan resolution now uses `MaaStageService.resolve_first_open_stage()` from the managed placeholder projection layer.
- Infrast time-rotation plan resolution uses local current time and the `period` values in the selected custom schedule JSON. If no active plan matches, it falls back to the first plan.
