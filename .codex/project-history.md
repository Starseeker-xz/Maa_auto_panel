# Project History

This is the concise handoff state for future sessions. Source session ids are listed on each entry.

## Current Repository State

- Confirmed (`2026-06-29_2137-project-state-docs`): Repository path is `/root/Linux_maa`; branch is `main`; current HEAD is `c5e42b6`.
- Confirmed (`2026-06-29_2137-project-state-docs`): Python project `linux-maa` requires Python `>=3.12` and is managed with `uv`.
- Confirmed (`2026-06-29_2137-project-state-docs`): Main CLI entry is `linux-maa = linux_maa.cli:main`.
- Confirmed (`2026-06-29_2137-project-state-docs`): Primary source packages are split by domain:
  - `src/linux_maa/android/`: ADB helpers.
  - `src/linux_maa/game/`: Bilibili Arknights APK/update logic.
  - `src/linux_maa/maa/`: project-local maa-cli runtime, generated config, run manager, and log translation hook.
  - `src/linux_maa/config/`: managed maa-cli config discovery and task item metadata extraction.
  - `src/linux_maa/web/`: FastAPI WebUI/API.
- Confirmed (`2026-06-29_2137-project-state-docs`): Thin compatibility modules still exist at `src/linux_maa/adb.py`, `constants.py`, `game_update.py`, and `maa_runner.py`.

## Product Direction

- Confirmed (`2026-06-29_2137-project-state-docs`): This project is still in an early-stage architecture/form-finding phase. When a subsystem needs redesign or dependency/runtime upgrade, prefer improving the overall architecture and environment directly over preserving obsolete behavior.
- Confirmed (`2026-06-29_2137-project-state-docs`): Because the project is early-stage, stale features should usually be deleted or replaced when they block a cleaner architecture. Do not keep old code as fallback unless there is a concrete current operational need.
- Confirmed (`2026-06-26_1620-maa-cli-framework-docs`): Long-term goal is a Docker-packaged high-availability Web UI framework around `maa-cli`/MaaCore automation for Arknights on redroid, not just an APK update script.
- Confirmed (`2026-06-26_1620-maa-cli-framework-docs`): Framework should schedule and call `maa-cli`; direct MaaCore integration is not the primary implementation path, although direct callbacks were explored.
- Confirmed (`2026-06-26_1620-maa-cli-framework-docs`): Failure handling should be coarse and pragmatic: parse `maa-cli` output/logs, retry/fallback by task/phase, and broadly recover Android/ADB instead of over-diagnosing every instability cause.
- Confirmed (`2026-06-26_1620-maa-cli-framework-docs`): Desired future behavior includes task-level retry policy, non-critical step handling, rerunning prerequisite steps before retry, notification on repeated blocking failures, and scheduled pauses/retries.
- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): User wants a GUI-like Web UI with configuration authoring, task execution, and eventually a visual editor for JSON/TOML-style framework and MAA config.

## Runtime and Environment

- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): Project-local `maa-cli` and MaaCore runtime are installed under ignored `runtime/maa/`.
- Confirmed (`2026-06-29_2137-project-state-docs`): `scripts/maa-env maa version` reports `maa-cli v0.7.5` and `MaaCore v6.12.2`.
- Confirmed (`2026-06-29_2137-project-state-docs`): Editable MAA/framework config now lives under tracked `config/maa/`; ignored `runtime/maa/` remains for downloaded binaries/resources, cache, generated sanitized configs, logs, and local state.
- Confirmed (`2026-06-29_2137-project-state-docs`): Current config files are:
  - `config/maa/profiles/default.toml`
  - `config/maa/tasks/test.toml`
  - `config/maa/tasks/startup-smoke.toml`
  - `config/maa/tasks/full-current.toml`
  - `config/maa/infrast/排班.json`
- Confirmed (`2026-06-29_2137-project-state-docs`): Default profile targets ADB serial `192.168.5.151:5555`, package `com.hypergryph.arknights.bilibili`, client `Bilibili`, connection config `CompatPOSIXShell`, touch mode `ADB`, and CPU OCR.
- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): `MaaTouch` caused a `NullPointerException` on redroid during earlier tests; keep `touch_mode = "ADB"` unless retesting/fixing MaaTouch intentionally.
- Confirmed (`2026-06-29_2232-config-editing`): Active development WebUI process was restarted on the normal port `8000` as `uv run linux-maa webui --host 0.0.0.0 --port 8000`.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): Active development WebUI process is running on `http://0.0.0.0:8000` from exec session `32056`, uvicorn PID `30808`, after a restart to load the managed Fight "当前/上次" sentinel change.
- Confirmed (`2026-06-30_1752-maa-cli-sequential-analysis`): Active development WebUI process was restarted on `http://0.0.0.0:8000` from exec session `86518`, server PID `46141`, after adding structured log entries, configurable panel-rule scaffolding, preprocessing log events, and single-shot main-run behavior.
- Confirmed (`2026-06-29_2137-project-state-docs`): Local frontend toolchain is Node `v22.23.1` and npm `10.9.8`.
- Confirmed (`2026-06-30_0124-config-save-delete`): Browser-based frontend visual checks are installed. `frontend` has dev dependency `playwright@^1.61.1`; Chromium/Chrome for Testing is cached under `/root/.cache/ms-playwright/`; Debian rendering dependencies such as fonts, Xvfb, NSS, Pango/Cairo, XKB, and AT-SPI libraries were installed through `npx playwright install --with-deps chromium`.

## Current Features

- Confirmed (`2026-06-26_1620-maa-cli-framework-docs`): `linux-maa update-game` fetches Bilibili Android package metadata, checks installed target version, reuses APK cache, can apply Bilibili incremental patches through `hdiffpatch`, falls back to full APK download, installs through ADB, and verifies installed version code.
- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): `linux-maa run-maa-task <task>` is a coarse retry wrapper for `maa-cli`, with per-attempt logs under `runtime/maa/run-logs/`, timeout handling, ADB reconnect, optional game force-stop, HOME key recovery, and retries.
- Confirmed (`2026-06-29_2137-project-state-docs`): Task files may contain framework metadata under each task's `[tasks.linux_maa]` namespace. Because raw `maa-cli` rejects unknown fields, the framework runner generates sanitized JSON task configs under `runtime/maa/generated-configs/<run-id>/tasks/` and symlinks non-task config directories.
- Confirmed (`2026-06-29_2137-project-state-docs`): `config/maa/tasks/test.toml` has explicit per-task `linux_maa.id` values: `startup`, `award`, `mall`, `infrast`, `fight`, and `recruit`.
- Confirmed (`2026-06-29_2137-project-state-docs`): FastAPI backend exposes config listing/reading, active run start/poll/stop, and SPA fallback serving for React Router routes.
- Confirmed (`2026-06-29_2232-config-editing`): Task-config reading now returns parsed `task_items` with `params`, `variants`, `linux_maa` metadata, and validation state. Validation strips `linux_maa` before applying `docs/maa-cli/schemas/task.schema.json`, then validates framework metadata separately.
- Confirmed (`2026-06-29_2232-config-editing`): Framework task metadata schema currently supports `id`, `unlimited_runs`, `min_daily_successes`, and `important`. Scheduling metadata is documented for future scheduled-run behavior but is not enforced by the runner yet.
- Confirmed (`2026-06-29_2137-project-state-docs`): WebUI has one in-memory active-run manager. It does not persist run history yet and does not support concurrent runs.
- Confirmed (`2026-06-29_2137-project-state-docs`): WebUI runs `maa-cli` with `--log-file=<path>` and verbosity selected by `log_level` (`0` summary only, `1` `-v`, `2` `-vv`, `3` `-vvv`).

## Frontend State

- Confirmed (`2026-06-26_2030-separate-frontend`): Frontend is a separate React + TypeScript + Vite app under `frontend/`; FastAPI serves `frontend/dist` when built.
- Confirmed (`2026-06-29_2232-config-editing`): Frontend now depends on JSON Forms (`@jsonforms/core`, `@jsonforms/react`, `@jsonforms/vanilla-renderers`) for schema-driven task-parameter editing.
- Confirmed (`2026-06-29_2137-project-state-docs`): Frontend uses React Router routes `/`, `/tasks/:taskConfig`, `/tasks/:taskConfig/items/:taskItemId`, `/schedule`, and `/settings`.
- Confirmed (`2026-06-29_2137-project-state-docs`): UI uses local shadcn-style components, Radix primitives, lucide icons, Tailwind CSS v4, `@tailwindcss/vite`, and `tw-animate-css`.
- Confirmed (`2026-06-30_0014-task-editor-fixes`): Main page is a three-column operational layout:
  - left: task config selector with local add panel, task item list with enable toggles, hover rename/delete controls, drag/drop handles, local add-task dropdown, start/stop controls;
  - center: schema-driven task editor with general/advanced tabs, Linux MAA metadata editing, validation display, and JSON Forms controls backed by per-task templates in `frontend/src/config/task-editor-schemas/*.json`;
  - right: status/log panel.
- Confirmed (`2026-06-30_0124-config-save-delete`): Frontend task-config edits are now staged as drafts and can be explicitly saved to the backend. The main page shows save/reset controls after staged changes. Running a task still uses the saved config file on disk, so unsaved drafts do not affect `maa-cli`.
- Confirmed (`2026-06-30_0124-config-save-delete`): Main-page selected task config is URL-derived only. A prior duplicate local `taskConfig` state caused navigation to be overwritten back to the initial route, which locked the page on `/tasks/award-no-mail`.
- Confirmed (`2026-06-30_0124-config-save-delete`): Backend task-config saving uses `PUT /api/configs/tasks/{name}`, rebuilds structured TOML/JSON from task items, validates before writing, and depends on `tomli-w` for TOML output. Visual TOML saves do not preserve original comments or hand formatting.
- Confirmed (`2026-06-30_0124-config-save-delete`): Backend config deletion uses `DELETE /api/configs/{kind}/{name}` and moves files to `config/maa/.trash/<timestamp>-<stem>-<token>/...` with `trash-record.json`; `config/maa/.trash/` is gitignored. The reusable trash logic lives in `src/linux_maa/storage/trash.py`.
- Confirmed (`2026-06-30_0124-config-save-delete`): Settings API now exposes `GET/PUT /api/settings`, combining framework settings, default Profile, and maa-cli config. Maa profile/cli settings are validated against local schemas before writing.
- Confirmed (`2026-06-30_0124-config-save-delete`): Framework settings are stored under `config/linux-maa/settings.toml` and currently include timezone mode, manual/browser timezone fields, scheduler placeholder, theme mode, and theme color. Auto timezone uses the backend/container timezone; browser timezone uses the client-reported IANA name; manual timezone supports fixed UTC offsets and IANA names such as `Europe/London` for DST-aware resolution.
- Confirmed (`2026-06-30_0124-config-save-delete`): "Game day offset" is not a user-facing setting. It was only an example during design discussion and should not be reintroduced into settings UI.
- Confirmed (`2026-06-30_0124-config-save-delete`): Maintenance actions are managed separately from normal task runs. `core-update` invokes `maa update --batch` for MaaCore and bundled/base resources, `resource-update` invokes `maa hot-update --batch` for MaaResource hot-update content, and `cli-update` invokes `maa self update --batch`. Only one maintenance action runs at a time.
- Confirmed (`2026-06-30_0124-config-save-delete`): `GET /api/maintenance/update-info` compares local `maa version`, local resource metadata, MaaCore/maa-cli version APIs, and MaaResource git remote commit so the UI can show update state before the user confirms an update.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): Backend exposes `GET /api/maa/stages` for the MAA GUI-style Fight stage candidate list. It reads local `runtime/maa/cache/maa/StageActivityV2.json`, maps `Bilibili` to `Official` like GUI, merges activity stages with GUI-equivalent permanent/resource stages, filters to currently open non-hidden stages by default, and supports `include_unavailable=true`.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): Task params can now be framework-managed through `linux_maa.managed_params`. On save, managed arrays become `__linux_maa_runtime__:array:<key>`, managed Fight stages become `__linux_maa_runtime__:fight_stage`, and Infrast plan selection becomes `__linux_maa_runtime__:infrast_plan_index`. On run, the framework resolves these placeholders before generating the raw maa-cli task config, strips `linux_maa`, and disables/skips a child task if an unknown or unresolvable runtime placeholder remains.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): Managed array resolution is generic: metadata stores ordered `{value, enabled}` items, while the runtime handler restores only enabled values into `tasks.params`. This replaces the previous UI behavior where unchecked array rows were deleted.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): Existing writable task configs under `config/maa/tasks/` were migrated through the same backend save path, so `test.toml`, `startup-smoke.toml`, and `full-current.toml` now persist managed values as placeholders plus `linux_maa.managed_params` metadata.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): Managed Fight stage plans are wired into the runner. The visual editor stores a candidate list, the saved task param is a placeholder, and the runner calls `MaaStageService.resolve_first_open_stage()` to write the first currently open candidate as MaaCore's single `Fight.stage` value.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): Fight "当前/上次" is no longer represented as an empty UI/API value. `/api/maa/stages` returns `value = "__linux_maa_stage__:current_last"` and `maa_value = ""`; metadata stores the non-empty framework value so it can be selected, ordered, and used as a fallback, while the runner maps it back to MaaCore's empty `stage` immediately before invoking `maa-cli`.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): Backend exposes Infrast dynamic option APIs: `GET /api/maa/infrast/files` lists custom schedule JSON files under `config/maa/infrast/` plus an explicit "not selected" option, and `GET /api/maa/infrast/plans?filename=...` reads plan names/periods from the selected file and prepends a time-based auto option. The runner resolves the auto option to the active plan index by checking each plan `period` against current local time.
- Confirmed (`2026-06-30_0124-config-save-delete`): WebUI public run-start API now accepts only `task`, `profile`, and `log_level`. Retry/timeout remains in the separate CLI wrapper internals, not in WebUI settings or frontend run payloads.
- Confirmed (`2026-06-30_1752-maa-cli-sequential-analysis`): WebUI run logs now pass through a stateful backend translator instead of a stateless passthrough. The first parsed semantics are configurable through `MaaLogPanelRule`; the default rule opens a panel on `TaskName Start` and closes it on `TaskName Completed`, `TaskName Error`, or `TaskName Stopped`. Run-state JSON includes structured `log_entries` for frontend timeline-card rendering plus `task_results` with per-child status. Task panel borders are status-driven: running uses the theme color, success uses ordinary border, failure uses warning color. Already translated events do not display the original raw maa-cli line, and visible run logs no longer include the full `maa run ...` command.
- Confirmed (`2026-06-30_1752-maa-cli-sequential-analysis`): WebUI main-page manual runs are single-shot and no longer apply a WebUI-level timeout or retry loop. The standalone CLI wrapper `linux-maa run-maa-task` still has its coarse attempts/timeout behavior.
- Confirmed (`2026-06-30_1752-maa-cli-sequential-analysis`): Framework preprocessing events are now inserted into structured run logs before `maa-cli` starts. Current events include resolved Fight stage and Infrast plan.
- Confirmed (`2026-06-30_1743-fix-infrast-plan-select`): Task item ids are fixed identifiers. Newly created frontend task items get a readable prefix plus random 8-hex suffix once at creation. Backend read preserves `linux_maa.id` after slug normalization and only appends `-2`, `-3`, etc. when ids collide within the same task list; it no longer recomputes ids from task-content hashes.
- Confirmed (`2026-06-30_0014-task-editor-fixes`): New local task-item defaults live in `frontend/src/config/task-item-defaults.json`; task workspace helpers for local config response, reindexing, renaming, delete, and enable toggles live in `frontend/src/lib/taskWorkspace.ts`.
- Confirmed (`2026-06-30_0014-task-editor-fixes`): JSON Forms renderer supports UI-only schema extensions `x-enabledWhen` and `x-disabledWhen`, plus titled `oneOf` enum values. These are frontend display/editing helpers and should not be serialized into maa-cli task params.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): JSON Forms renderer now supports `x-linuxMaaManaged` and `x-optionsSource`. Managed arrays show enable checkboxes and keep disabled rows in metadata; ordinary arrays do not get checkboxes. Dynamic select options come from backend APIs. Radix select empty-value options are encoded internally so Fight's "当前/上次" and Infrast's "不选择自定义排班文件" do not crash the select menu.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): Infrast `filename` and `plan_index` are in the general settings tab as dropdowns. `filename` options come from `/api/maa/infrast/files`; `plan_index` options come from `/api/maa/infrast/plans`; `plan_index` is disabled when no custom schedule file is selected. The first plan option can be the backend-driven time-rotation auto placeholder.
- Confirmed (`2026-06-30_1743-fix-infrast-plan-select`): Infrast `plan_index` dynamic select now updates the visible selected label immediately. The fix routes runtime-value dynamic select changes through a combined params + `linux_maa.managed_params` callback in `ConfigEditorPane`, avoiding separate draft updates that can overwrite each other with stale task item snapshots.
- Confirmed (`2026-06-30_0124-config-save-delete`): Primitive JSON Forms arrays now use reusable `frontend/src/components/PrimitiveArrayEditor.tsx`. It supports framed array sections, plus-button add, row checkboxes, hover delete, drag sorting, free-value rename, and enum dropdown editing. `uniqueItems` enum rows show all allowed values and swap with an existing row when needed to preserve uniqueness.
- Confirmed (`2026-06-29_2232-config-editing`): `docs/maa-cli/config_examples/tasks/full-current.toml` is a broad reference config for the current maa-cli task enum and MaaCore `integration.md` params. It passed the local maa-cli task JSON Schema validation.
- Confirmed (`2026-06-29_2232-config-editing`): MAA GUI candidate Fight stages are a GUI-layer `StagePlan`, not a MaaCore params schema feature. The GUI loads `gui/StageActivityV2.json` and `resource/tasks/tasks.json`, then serializes the first currently open stage into MaaCore's single `stage` param.
- Confirmed (`2026-06-29_2137-project-state-docs`): Sidebar pages are `主界面`, `定时执行`, and `设置`; schedule/settings are placeholders.
- Confirmed (`2026-06-30_0124-config-save-delete`): Settings page is now an implemented parallel-panel layout, not a tabbed/subpage layout. Panels cover framework/timezone, default Profile, maa-cli/resource update settings, maintenance action output, and theme mode/color.
- Confirmed (`2026-06-30_0124-config-save-delete`): Settings page ordinary-user UI intentionally hides MaaCore component split toggles, maa-cli binary component toggle, SSH update options, and profile custom/global/platform resource controls. Hidden maa-cli component settings are normalized to full-install values on settings load/save to avoid partial MaaCore/base-resource installations.
- Confirmed (`2026-06-30_0124-config-save-delete`): Settings descriptions use question-mark tooltips rather than inline explanatory text under every field. Theme controls are in the framework card and apply immediately through browser localStorage without requiring the settings save action.
- Confirmed (`2026-06-30_0124-config-save-delete`): Update-info UI keeps update concepts separate: MaaCore/base package version (`maa update`), maa-cli version (`maa self update`), hot-resource git commit (`maa hot-update`), local base resource file metadata, and local hot-resource file metadata. Do not compare base resource `version.json:last_updated` to MaaCore release `published_at`.
- Confirmed (`2026-06-30_0124-config-save-delete`): Save/reset confirmation controls are shared through `frontend/src/components/DirtyActions.tsx` and used by both main task editing and settings editing.
- Confirmed (`2026-06-30_0124-config-save-delete`): Theme application uses CSS variables and `frontend/src/lib/theme.ts`; App loads locally stored theme first, then backend theme if no local override exists, and responds to system dark-mode changes when mode is `system`. Theme changes apply immediately and do not require the settings save action.
- Confirmed (`2026-06-30_0124-config-save-delete`): Sidebar "主界面" navigation restores the last main task route from `localStorage` key `linux-maa:last-main-path`, preventing a return from settings/schedule from jumping to the first sorted config.
- Confirmed (`2026-06-26_2030-separate-frontend`): Profile selection is intentionally hidden from the main page for now; frontend submits profile `default`.

## Important Observations

- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): Target Android environment is redroid CT `151` at `192.168.5.151:5555`, Android 14 x86_64, screen `1280x720`, density `240`, SELinux disabled.
- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): First full real `test` run had StartUp succeed, then Award/Mall/Fight/Recruit fail. Award entered mail flow and repeatedly detected loading text; saved failure screenshot showed Android launcher/home, suggesting app backgrounding/input-layer failure rather than a simple game process crash.
- Likely (`2026-06-26_1702-setup-maa-cli-test`): Mall/Fight/Recruit failures in that run were cascade failures after Award left the game in a bad or unrecognized state.
- Confirmed (`2026-06-26_1727-webui-config-runner`): Direct MaaCore ctypes experiment in session scratch showed structured callbacks are available, but project direction remains `maa-cli` wrapper first.
- Confirmed (`2026-06-26_1727-webui-config-runner`): MaaCore `AsstLoadResource` must receive a base directory containing `resource/`, such as `runtime/maa/data/maa`, not `runtime/maa/data/maa/resource`.
- Likely (`2026-06-26_1727-webui-config-runner`): Better user-facing progress should eventually come from selected `maa-cli` summary/log events or MaaCore callback-like parsing, not raw `asst.log`.
- Confirmed (`2026-06-26_1727-webui-config-runner`): WebUI deliberately does not stream low-level `runtime/maa/state/maa/debug/asst.log` into normal UI output.
- Confirmed (`2026-06-30_0124-config-save-delete`): Current local runtime resource files report `砺火成锋` with raw `last_updated = 2026-06-26 10:29:15.000`; local and remote MaaResource main commits both equal `e0130203bc6e97911b8e8f9863a87d7fd0470537`. MAA GUI parses `last_updated` as UTC and displays local time; GUI's 2026-06-28 build date is software/Core build metadata, not resource metadata.
- Confirmed (`2026-06-30_0124-config-save-delete`): Playwright screenshots of `/settings` at `1440x1000` and `520x900` found no horizontal overflow. Screenshot files for that check are in `.codex/conversations/2026-06-30_0124-config-save-delete/scratch/`.

## Documentation State

- Confirmed (`2026-06-29_2137-project-state-docs`): Project-owned descriptive files and their current roles:
  - `README.md`: root quickstart and current user-facing project overview.
  - `docs/README.md`: documentation index and high-value upstream reference map.
  - `docs/maa-runtime.md`: current project-local `maa-cli`/MaaCore runtime, managed config layout, WebUI runner behavior, and operational notes.
  - `docs/architecture-direction.md`: intended architecture, tradeoffs, stack direction, and future workflow/scheduling model.
  - `docs/maa-reading-notes.md`: first-pass reading notes for MAA/maa-cli integration.
  - `.codex/project-history.md`: durable current state and future handoff facts.
  - `.codex/project-lessons.md`: recurring project-specific traps and safer defaults.
  - `.codex/conversations/index.md` and `.codex/conversations/<session-id>/session.md`: session index and session-local detail.
- Confirmed (`2026-06-29_2137-project-state-docs`): Whenever code, config layout, runtime behavior, dependencies, CLI commands, WebUI routes, or frontend architecture changes, check whether the descriptive files above need updates in the same change. Avoid letting docs/history describe an older architecture.
- Confirmed (`2026-06-26_1620-maa-cli-framework-docs`): Mirrored upstream MAA docs live under `docs/maa-upstream/zh-cn/`; selected maa-cli schemas/examples live under `docs/maa-cli/`.
- Confirmed (`2026-06-29_2137-project-state-docs`): `docs/maa-runtime.md` is the main current runtime/config handoff document.

## Next Promising Directions

- Implement persistent run records and history (likely SQLite) before expanding scheduling behavior.
- Add a real workflow/retry policy model instead of only whole-task `attempts`.
- Confirmed (`2026-06-30_1752-maa-cli-sequential-analysis`): Upstream `maa-cli` custom-task execution creates one MaaCore `Assistant`, appends all active child tasks, connects once, calls `start()` once, waits for all tasks, then stops/destroys the assistant. Splitting Linux MAA orchestration into one child task per `maa-cli` invocation will repeat update checks/profile/resource/core setup/ADB connect/assistant lifecycle per child, and makes exit code/log/summary/retry boundaries per child instead of per whole custom task.
- Confirmed (`2026-06-30_1752-maa-cli-sequential-analysis`): `maa-cli` applies whole-file preprocessing before execution: variant activation, client-type inference/normalization, startup/closedown auto-prepend/append, and relative filename normalization. If Linux MAA generates one-child task files, it must intentionally preserve or replace any of those whole-file semantics it still needs.
- Build config editing incrementally: first task item enable/disable and selected task params, then schema-driven form editing, then raw editor toggle if needed.
- Add selected log parsing/translation in `src/linux_maa/maa/logs.py` so UI shows higher-level events without exposing raw MaaCore debug logs.
- Add status APIs for ADB/redroid, Maa runtime/resource versions, generated config paths, and recent run logs.
- Add targeted tests around `prepare_maa_cli_task`, metadata stripping, config resolution, task item id stability, and run manager process state.

## Scheduled Execution / Retry Planning

- Confirmed (`2026-06-30_1934-scheduled-retry-architecture`): Framework task metadata now accepts and preserves `retry_even_success`. The visual task editor exposes it as “成功也参与重试”; new StartUp and CloseDown task defaults set it true; existing `startup-smoke`, `test`, and `full-current` StartUp/CloseDown examples have the field where applicable. The current manual WebUI runner still ignores scheduling metadata.
- Confirmed (`2026-06-30_1934-scheduled-retry-architecture`): `pytest` was added as a uv dev dependency because the repository had tests but `uv run pytest` could not spawn pytest. After the change, `uv run pytest` passes 8 tests.
- Likely (`2026-06-30_1934-scheduled-retry-architecture`): The next scheduler implementation should add a pure domain/policy layer before process orchestration: scheduled configs bind `{task_config, profile, cron/times, hooks/scripts}`, daily child-task success counters, per-run attempt records, and a retry planner that selects child tasks based on `important`, `unlimited_runs`, `min_daily_successes`, and `retry_even_success`.
- Likely (`2026-06-30_1934-scheduled-retry-architecture`): The current single `MaaRunManager` should remain a manual-run process adapter temporarily. Scheduled execution should use a new orchestration service that can generate per-attempt task configs from a selected child-task subset, call the same maa-cli process primitives, persist attempt results, and feed log parsing into durable run history.
- Hypothesis (`2026-06-30_1934-scheduled-retry-architecture`): SQLite should be introduced before or together with scheduling, because retry decisions require durable same-day success state across backend restarts and need auditability beyond the current in-memory active run.
