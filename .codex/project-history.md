# Project History

This is the compact handoff state for future sessions. It intentionally omits old scratch logs, screenshots, upstream source checkouts, and step-by-step implementation history. Source session ids are listed on entries.

## Current Repository State

- Confirmed (`2026-06-30_2342-full-project-audit`): Repository path is `/root/Linux_maa`; branch is `main`; baseline HEAD at the start of the full audit was `6c7b851`.
- Confirmed (`2026-06-29_2137-project-state-docs`): Python project `linux-maa` requires Python `>=3.12`, uses `uv`, and exposes CLI entry `linux-maa = linux_maa.cli:main`.
- Confirmed (`2026-06-30_2342-full-project-audit`): Frontend is React + TypeScript + Vite under `frontend/`; FastAPI serves `frontend/dist` for SPA routes when built.
- Confirmed (`2026-06-30_2342-full-project-audit`): Main local config files are:
  - `config/linux-maa/settings.toml`
  - `config/linux-maa/schedules/daily-test.toml`
  - `config/maa/cli.toml`
  - `config/maa/profiles/default.toml`
  - `config/maa/tasks/General.toml`
  - `config/maa/tasks/full-current.toml`
  - `config/maa/tasks/startup-smoke.toml`
  - `config/maa/tasks/test.toml`
  - `config/maa/infrast/排班.json`
- Confirmed (`2026-06-30_2342-full-project-audit`): `config/linux-maa/settings.toml` currently has `framework.scheduler.enabled = true`. This supersedes older history that said the scheduler was disabled.

## Product Direction

- Confirmed (`2026-06-26_1620-maa-cli-framework-docs`): Long-term goal is a Docker-packaged WebUI framework around `maa-cli`/MaaCore automation for Arknights on redroid, not a standalone APK updater.
- Confirmed (`2026-06-26_1620-maa-cli-framework-docs`): Framework should schedule and call `maa-cli`; direct MaaCore integration was explored but is not the primary path.
- Confirmed (`2026-06-29_2137-project-state-docs`): The project is still early-stage. Prefer simplifying architecture and deleting obsolete fallback paths when they block a cleaner design.
- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): User wants a GUI-like Web UI with configuration authoring, task execution, scheduled execution, and practical retry/recovery behavior.

## Runtime And Environment

- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): Project-local `maa-cli` and MaaCore runtime are installed under ignored `runtime/maa/`.
- Confirmed (`2026-07-01_2153-manage-service-history`): The old detached WebUI listener on `http://0.0.0.0:8000/` was stopped after verifying `127.0.0.1:8000/api/settings` served this project. The stale ignored PID file `runtime/linux-maa/webui.pid` contained `4` and was removed. WebUI lifecycle is now temporarily managed by systemd unit `/etc/systemd/system/linux-maa-webui.service`, command `/root/.local/bin/uv run linux-maa webui --host 0.0.0.0 --port 8000`, working directory `/root/Linux_maa`. The unit is registered, valid, `disabled`, and currently `inactive`; port 8000 is free.
- Confirmed (`2026-06-30_2318-gpu-ocr-research`): `scripts/maa-env maa version` reported `maa-cli v0.7.5` and `MaaCore v6.13.0`.
- Confirmed (`2026-06-30_2056-scheduled-execution`): Default profile currently targets ADB serial `192.168.5.151:5555`, package `com.hypergryph.arknights.bilibili`, client `Bilibili`, connection config `CompatPOSIXShell`, touch mode `MaaTouch`, and CPU OCR.
- Confirmed (`2026-06-30_2318-gpu-ocr-research`): Current machine has NVIDIA RTX 2080 Ti and Intel iGPU visible, but the packaged MaaCore runtime only exposes CPU ONNXRuntime provider symbols. GPU OCR config reaches MaaCore but logs `use_gpu No GPU execution provider available`.
- Confirmed (`2026-06-30_0124-config-save-delete`): Playwright/Chromium visual checks are available from the frontend dev dependency and cached browser install.

## Backend Architecture

- Confirmed (`2026-06-30_2342-full-project-audit`): Backend modules are organized by domain:
  - `android/`: ADB helpers.
  - `game/`: Bilibili package metadata, APK/patch download, install/update flow.
  - `config/`: maa-cli config discovery, parsed task items, metadata/schema validation, app settings.
  - `maa/`: runtime discovery, process primitive, manual run manager, log translation, maintenance/update info, stage and Infrast dynamic option services.
  - `scheduler/`: schedule config, game-day time calculation, retry policy, script hooks, text-backed scheduled-run orchestration.
  - `history.py`: framework text/JSONL run history, high-level event logs, detailed process logs, scheduler counters/triggers, and retention.
  - `storage/`: recycle-bin/trash behavior for managed config files.
  - `web/`: FastAPI app factory, service bundle, response helpers, route modules.
- Confirmed (`2026-06-30_2342-full-project-audit`): Shared backend helper modules now exist:
  - `src/linux_maa/utils.py` for slug/path/atomic-write/version/dict/bounded-int helpers.
  - `src/linux_maa/state.py` for idle/current-state response helpers.
- Confirmed (`2026-06-30_2342-full-project-audit`): `src/linux_maa/web/app.py` was split into route modules under `src/linux_maa/web/routes/`, plus `web/services.py` and `web/responses.py`.
- Confirmed (`2026-06-30_2342-full-project-audit`): Backend audit report is `BACKEND_AUDIT.md`.

## API Surface

- Confirmed (`2026-06-30_2342-full-project-audit`): Main API groups are:
  - `GET /api/configs`
  - `GET/PUT /api/configs/tasks/{name}`
  - `DELETE /api/configs/{kind}/{name}`
  - `GET/POST /api/runs/current` via current/manual run endpoints
  - `POST /api/runs`
  - `POST /api/runs/{run_id}/stop`
  - `GET/POST /api/schedules`
  - `GET/PUT/DELETE /api/schedules/{schedule_id}`
  - `POST /api/schedules/{schedule_id}/run`
  - `GET /api/schedules/current`
  - `POST /api/schedules/current/stop`
  - `GET/PUT /api/settings`
  - `GET /api/maintenance/current`
  - `GET /api/maintenance/update-info`
  - `POST /api/maintenance/{kind}`
  - `GET /api/history/runs`
  - `GET /api/history/runs/{run_id}`
  - `GET /api/maa/stages`
  - `GET /api/maa/infrast/files`
  - `GET /api/maa/infrast/plans`
- Confirmed (`2026-07-02_2245-tools-page`): Tools API was added:
  - `GET /api/tools`
  - `GET /api/tools/current`
  - `GET /api/tools/current/events`
  - `POST /api/tools/current/stop`
  - `POST /api/tools/{tool_id}/run`
- Confirmed (`2026-06-30_2342-full-project-audit`): Public API paths were preserved during backend route splitting.

## Core Features

- Confirmed (`2026-06-30_2056-scheduled-execution`): Manual WebUI runs use `MaaRunManager`; scheduled execution uses `SchedulerService`. Both rely on shared maa-cli process primitives.
- Superseded (`2026-07-03_0105-audit-log-module`): maa-cli log handling used to live under `src/linux_maa/maa/logs/`; the implementation was moved to top-level `src/linux_maa/logs/` so WebUI-visible log behavior is no longer owned by maa run logic. The old `linux_maa.maa.logs` package is now only a compatibility export layer.
- Confirmed (`2026-07-01_2153-manage-service-history`): maa-cli logs to stderr by default, but with the current `maa-cli v0.7.5`, passing `--log-file` caused info lifecycle logs to be absent from stderr/stdout in a real `startup-smoke` run. WebUI/scheduled live runs therefore no longer pass `--log-file`. The shared `run_streaming_process()` primitive reads stdout and stderr from separate pipes; live UI still receives a merged ordered view for parsing/display, while detailed text logs store stdout and stderr in separate `debug/linux-maa/external/maa-cli/<run-id>.stdout.log` / `<run-id>.stderr.log` files. `MaaRuntime.env()` forces `MAA_LOG_PREFIX=Always` for parser-compatible stderr prefixes.
- Confirmed (`2026-07-01_1506-sse-log-delta`): Manual and scheduled current-run UI state now uses one full JSON snapshot plus incremental SSE. `GET /api/runs/current` and `GET /api/schedules/current` return full current state with `stream_version`; frontend opens `GET /api/runs/current/events` or `GET /api/schedules/current/events` with version/array cursors. SSE data events are `patch` payloads with `replace_from/items` for `output`, `task_results`, and `log_entries`; `reset` is reserved for no-cursor or recovery cases. Frontend merges patches locally. Scheduler overview/detail responses now embed only light current-run state without log arrays.
- Confirmed (`2026-07-01_1506-sse-log-delta`): `LogPane` now follows the newest log entry while the user is already near the bottom, and stops auto-scrolling when the user scrolls up. This fixed the observed case where `StartUp Start` was present in the backend log at `15:19:49` but not visible in the fixed-height log pane until later.
- Confirmed (`2026-06-30_1752-maa-cli-sequential-analysis`): Manual WebUI runs are single-shot and no longer apply a WebUI-level timeout/retry loop. The standalone CLI wrapper `linux-maa run-maa-task` still has coarse attempts/timeout behavior.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): Task params can be framework-managed through `linux_maa.managed_params`. Runtime placeholders are resolved before generating raw maa-cli task config.
- Confirmed (`2026-06-30_1626-maa-stage-candidates`): Fight stage candidates and Infrast plan options are backend-driven and exposed through `/api/maa/...` endpoints.
- Superseded (`2026-07-01_2153-manage-service-history`): An intermediate text-backed design stored run/scheduler state under `debug/linux-maa/history/` and mirrored human run events into `framework.log`; this was rejected because `debug/` must be disposable diagnostics and `framework.log` must be real framework debug logging.
- Confirmed (`2026-07-01_2153-manage-service-history`): Framework state and diagnostics are now separate. State lives under ignored `state/linux-maa/`: `run-history/recent-run-records.json`, `run-history/scheduled-run-attempts.json`, `scheduler/daily-task-stats.json`, and `scheduler/triggered-schedule-entries.json`. The old ignored `runtime/linux-maa/scheduler.sqlite3` was intentionally deleted with no migration.
- Confirmed (`2026-07-03_0105-audit-log-module`): Diagnostics live under ignored `debug/linux-maa/`. `framework.log` is configured through Python `logging` with DEBUG/INFO/WARNING/ERROR/CRITICAL and API request middleware. Human-level run events are JSONL under `debug/linux-maa/events/<run-id>.jsonl`. External logs are grouped by source, not manual/scheduled origin: `debug/linux-maa/external/maa-cli/<run-id>.stdout.log`, `<run-id>.stderr.log`, `debug/linux-maa/external/tools/<run-id>.stdout.log`, `.stderr.log`, `debug/linux-maa/external/scripts/<run-id>.stdout.log`, `.stderr.log`, and MaaCore captures under `debug/linux-maa/external/maacore/<run-id>.log`.
- Confirmed (`2026-07-02_2245-tools-page`): A generic backend `ToolRunManager` now powers the small-tools page. The initial registered tool is `game-update` / `更新游戏`, which runs `linux_maa.cli update-game` in a subprocess with the page-provided ADB serial and default Profile `adb_path`. Tool run state uses the shared current-run/SSE patch shape consumed by frontend `LogPane`.
- Confirmed (`2026-07-03_0105-audit-log-module`): Manual maa-cli runs, scheduled maa-cli runs, tool runs, and maintenance actions now use `linux_maa.logs.RunLogBuffer` for the WebUI-visible `output`, `task_results`, and `log_entries` shape. `RunLogTranslator` owns the MAA-aware parser, source-specific partial lines, summary/task grouping, framework events, git-output grouping, and terminal redraw collapse.
- Confirmed (`2026-07-02_2245-tools-page`): Tool runs are stored as `kind = "tool"` in `state/linux-maa/run-history/recent-run-records.json`; stdout/stderr diagnostics are under `debug/linux-maa/external/tools/<run-id>.stdout.log` and `.stderr.log`; high-level events use `debug/linux-maa/events/<run-id>.jsonl`.
- Confirmed (`2026-07-03_0105-audit-log-module`): `run_streaming_process()` preserves raw carriage returns using `TextIOWrapper(..., newline="")`, and `RunLogTranslator` collapses terminal redraw/progress output (`\r` and backspace/delete edits) into a single mutable line entry. This fixes `tqdm` download progress flooding without adding downloader-specific throttling.
- Confirmed (`2026-07-02_2245-tools-page`): The shared process primitive was renamed and moved from `linux_maa.maa.process.run_maa_cli_process()` / `MaaCliProcessResult` to `linux_maa.process.run_streaming_process()` / `StreamingProcessResult`, because it is now used by manual maa-cli, scheduled maa-cli, maintenance actions, and generic tools.
- Confirmed (`2026-07-02_2245-tools-page`): Latest tool run `cb97801d9dec` showed framework events arriving immediately but `update_game()` stdout only surfacing near process completion, because child Python stdout was block-buffered through `stdout=PIPE`. The game-update tool now launches as `sys.executable -u -m linux_maa.cli update-game ...`; future Python-based tools that need live UI logs should use unbuffered stdout or equivalent.
- Confirmed (`2026-07-02_2245-tools-page`): `ToolRunManager.start()` rejects new tool runs while the current run is `running` or `stopping`, preventing a direct API call from overlapping tool processes during stop.
- Superseded (`2026-07-03_0105-audit-log-module`): Earlier in this session, audit found visible-log behavior still depended on `MaaCliLogTranslator` under `linux_maa.maa.logs` and maintenance actions only exposed raw `output`. This was fixed later in the same session by moving the implementation to `linux_maa.logs`, introducing `RunLogBuffer`, and wiring maintenance actions into `log_entries`.
- Confirmed (`2026-07-03_0105-audit-log-module`): Schedule restart-script hooks now execute through `run_streaming_process()` rather than `subprocess.run(..., capture_output=True)`. Hook stdout/stderr stream live into the scheduled run's shared visible log through the plain parser, so arbitrary script text cannot accidentally become MAA task/summary entries. Raw hook streams are stored under `debug/linux-maa/external/scripts/`, and hook scripts run with `MaaRuntime.env()` so project-local `maa`, `MAA_CONFIG_DIR`, and XDG paths are available.
- Confirmed (`2026-06-30_2056-scheduled-execution`): Scheduled retry policy uses `important`, `unlimited_runs`, `min_daily_successes`, and `retry_even_success` metadata.
- Confirmed (`2026-06-30_0124-config-save-delete`): Config deletes move files into `.trash` records instead of hard deleting.
- Confirmed (`2026-06-30_0124-config-save-delete`): Maintenance actions are separate from normal runs and cover MaaCore/base resources, hot resources, and maa-cli self-update.

## Frontend Architecture

- Confirmed (`2026-06-30_2342-full-project-audit`): Frontend route shell lives in `App.tsx`; pages are `MainPage`, `SchedulePage`, `ToolsPage`, and `SettingsPage`.
- Confirmed (`2026-06-30_2342-full-project-audit`): Routes are `/`, `/tasks/:taskConfig`, `/tasks/:taskConfig/items/:taskItemId`, `/schedule`, `/schedule/:scheduleId`, `/tools`, and `/settings`.
- Confirmed (`2026-06-30_2342-full-project-audit`): Shared frontend helpers/components now include:
  - `components/FormFields.tsx`
  - `components/InsertionLine.tsx`
  - `lib/usePolling.ts`
  - `pages/schedule/ScheduleLeftPane.tsx`
  - `pages/schedule/ScheduleDetailPanels.tsx`
- Confirmed (`2026-06-30_2342-full-project-audit`): `SchedulePage` was split from roughly 797 lines to roughly 382 lines; page-level logic remains there, while left/detail panes moved under `pages/schedule/`.
- Confirmed (`2026-06-30_2342-full-project-audit`): Frontend audit report is `FRONTEND_AUDIT.md`.
- Confirmed (`2026-07-02_1933-config-sync-ui-schema`): `frontend/src/config/task-editor-schemas/*.json` is only the frontend visual editor schema for task params. Backend task config read/write/validation does not import those files. Removing a key from a task editor schema hides that field from JSON Forms but does not automatically remove an existing param from old configs; old params can round-trip through `task_items` unless explicit cleanup/migration is added. If a schema property is removed, also remove its key from the template's `general`/`advanced` list to avoid a dangling JSON Forms control.
- Confirmed (`2026-07-02_1933-config-sync-ui-schema`): Schedule detail page stats now refresh after a scheduled run completes. `SchedulePage` listens for the schedule run SSE state to transition out of `running`/`stopping`, refreshes schedule overview, and merges runtime detail fields (`daily_stats`, `recent_runs`, timeline/current-run related fields) for the visible schedule without overwriting the user's unsaved schedule draft. The schedule start button is disabled while a run is active, while no entry exists, and while the schedule draft is dirty because backend manual schedule runs use the saved schedule from disk.
- Confirmed (`2026-07-02_1933-config-sync-ui-schema`): `LogPane` no longer shows header-side `info` or always-visible log paths. It now has a lower-left details button that reveals run id, schedule/entry names, stdout/stderr log paths, legacy log path fallback, and preprocessing choices parsed from visible log entries (`选择战斗关卡:` / `选择基建计划:`).
- Confirmed (`2026-07-02_2245-tools-page`): `ToolsPage` is now a three-column UI using fixed tool list, config panel, and the shared `LogPane`; it has no drag/rename/delete logic. Supporting components live under `frontend/src/pages/tools/ToolListPane.tsx` and `frontend/src/pages/tools/ToolConfigPane.tsx`. The run/stop controls are in the middle config column footer, and the active tool list item shows a spinning loader.

## Full Audit Fixes

- Confirmed (`2026-06-30_2342-full-project-audit`): Backend duplicate helpers were consolidated across config, scheduler, maa runner/stages/infrast/maintenance, storage/trash, and game update manifest writing.
- Confirmed (`2026-06-30_2342-full-project-audit`): Fixed scheduler `create_schedule()` precedence bug so an explicit `task_config` is preserved even when no task configs are listed.
- Confirmed (`2026-06-30_2342-full-project-audit`): Frontend form field implementations in Settings/Profile were consolidated into `FormFields`.
- Confirmed (`2026-06-30_2342-full-project-audit`): Frontend drag insertion marker was consolidated into `InsertionLine`.
- Confirmed (`2026-06-30_2342-full-project-audit`): Frontend repeated polling moved to `usePolling`.
- Confirmed (`2026-06-30_2342-full-project-audit`): Fixed schedule-detail UI bug where changing bound task config left the task checklist showing stale `detail.task_config` until save/reload.
- Confirmed (`2026-06-30_2342-full-project-audit`): API error formatting now handles FastAPI detail arrays and project validation errors.

## Documentation And Reports

- Confirmed (`2026-06-30_2342-full-project-audit`): Root audit/cleanup reports created or planned in this audit session:
  - `BACKEND_AUDIT.md`
  - `FRONTEND_AUDIT.md`
  - `PROJECT_CLEANUP_AUDIT.md`
- Confirmed (`2026-06-29_2137-project-state-docs`): Keep `README.md`, `docs/README.md`, `docs/maa-runtime.md`, `docs/architecture-direction.md`, `.codex/project-history.md`, `.codex/project-lessons.md`, and the current session file in sync when architecture or workflows change materially.

## Known Constraints And Lessons

- Confirmed (`2026-06-30_0124-config-save-delete`): Main-page selected task config should remain URL-derived; do not reintroduce duplicate local selected-config state.
- Confirmed (`2026-06-30_1743-fix-infrast-plan-select`): JSON Forms controls that update visible `params` and `linux_maa.managed_params` must apply a combined update, or stale task item snapshots can overwrite the visible param change.
- Confirmed (`2026-06-30_2056-scheduled-execution`): Repository-wide `rg` should exclude `frontend/node_modules`, `docs/maa-upstream`, and `runtime`, or target relevant paths explicitly.
- Confirmed (`2026-06-30_2342-full-project-audit`): Do not track `.codex/conversations/**/scratch/`, `frontend/.codex/`, or local debug captures. Durable findings belong in history/session files; raw artifacts belong in ignored scratch.

## Remaining Risks

- Confirmed (`2026-07-02_2144-manual-stop-delay`): Manual stop delay around the UI "已连接" line was reproduced and traced to MaaCore/ADB cold-start behavior, not a frontend display delay. Runs `e87fa44a4cee`, `3af525bb11ac`, and reproduced run `2636bb1ed39e` all had no local ADB server at connect start; MaaCore failed adb-lite connection to 127.0.0.1:5037, fell back to NativeIO, waited 60001 ms on `adb devices`, then emitted `Connected` and only then surfaced the earlier stop request. Warm comparison run `3f8150aa6912` had ADB server already listening, `adb devices` cost 0 ms, `async_connect` took 551 ms, and manual stop finalized about 0.5 s after the stop request.
- Confirmed (`2026-07-02_2144-manual-stop-delay`): Current manual profile `config/maa/profiles/default.toml` has `adb_lite_enabled = true` and `kill_adb_on_exit = true`; schedule profile in `config/linux-maa/schedules/daily-test.toml` has `adb_lite_enabled = false` but `kill_adb_on_exit = true`. Older scheduled MaaCore logs also show the same 60001 ms `adb devices` cold-start delay, so disabling adb-lite alone is insufficient. `kill_adb_on_exit = true` makes cold ADB server state recur after maa-cli exits.
- Likely (`2026-07-02_2144-manual-stop-delay`): Best mitigation direction is to keep or prestart local ADB server before maa-cli runs (`adb start-server` / `adb connect 192.168.5.151:5555`, plus consider `kill_adb_on_exit = false`) and make manual stop use the existing `run_streaming_process(... should_stop=...)` terminate-then-kill fallback instead of only calling `Popen.terminate()`.
- Confirmed (`2026-07-01_2153-manage-service-history`): `SettingsPage` is still large at 658 lines; it remains a candidate to split into framework/profile/maintenance cards.
- Confirmed (`2026-07-01_2153-manage-service-history`): `PrimitiveArrayEditor` is still high-density at 390 lines; split only if it grows again or logic becomes harder to test.
- Confirmed (`2026-07-01_2153-manage-service-history`): `ConfigEditorPane` and schedule/settings dirty checks still use `JSON.stringify` (`ConfigEditorPane.tsx`, `SchedulePage.tsx`, `SettingsPage.tsx`). This remains acceptable for current controlled objects, but replace with stable deep equality if arbitrary user JSON editing expands.
- Confirmed (`2026-07-01_2153-manage-service-history`): Frontend bundle still triggers Vite's 500 kB chunk warning. `npm run build` produced `dist/assets/index-DvZApfPE.js` at 752.15 kB minified / 240.10 kB gzip; consider lazy routes/manual chunks later.
- Confirmed (`2026-07-03_0105-audit-log-module`): Live structured `log_entries`, task records, task messages, and record raw lines are bounded in `RunLogTranslator`/`RunLogBuffer`; detailed diagnosis belongs in `debug/linux-maa/framework.log`, external stdout/stderr logs grouped by source, and MaaCore `asst.log` excerpts rather than unbounded UI state.
- Superseded (`2026-07-03_0105-audit-log-module`): A prior risk noted that `MaaCliLogTranslator` could clear stdout summary state when stderr emitted timestamped lifecycle lines. The parser is now `RunLogTranslator`, still source-aware, and keeps partial lines, active task, active summary, and active git-output blocks per source.
- Confirmed (`2026-07-03_0105-audit-log-module`): SSE reconnect recovery still resends full `log_entries` when the client version is behind; normal online SSE still sends first-difference array patches.
- Confirmed (`2026-07-02_1933-config-sync-ui-schema`): Log translation now covers current sanity, mission start/sanity use, drops/furni, recruit result/tag status, facility entry/product names, base-shift operators, product changes, and base-shift summary lines such as `Trade(SyntheticJade) with operators: ...`. Git fetch/update output starting with `From https://github.com/`, `Updating <rev>..<rev>`, or `Already up to date.` is grouped as a `资源拉取结果` structured block.

## Latest Verification

- Confirmed (`2026-06-30_2342-full-project-audit`): After backend refactor, `uv run python -m compileall -q src tests` passed and `uv run pytest -q` passed 25 tests.
- Confirmed (`2026-06-30_2342-full-project-audit`): After frontend refactor, `cd frontend && npm run build` passed with only the existing Vite large chunk warning.
- Confirmed (`2026-06-30_2342-full-project-audit`): Vite preview plus Playwright mock-API smoke passed for `/tasks/test/items/startup`, `/schedule/daily-test`, and `/settings` at desktop `1440x1000` and mobile `390x844`, with no horizontal overflow detected.
- Confirmed (`2026-07-01_1506-sse-log-delta`): After log-delta SSE changes and LogPane follow-tail fix, `uv run python -m compileall -q src tests`, `uv run pytest -q` (28 tests), and `cd frontend && npm run build` passed. Runtime smoke on restarted WebUI confirmed `/api/runs/current` and `/api/schedules/current` return `stream_version`, and an SSE request with `after=0` while idle produced no immediate full data payload before a 2-second timeout. Running WebUI `/` serves frontend bundle `assets/index-DvZApfPE.js`.
- Confirmed (`2026-07-01_2153-manage-service-history`): `systemd-analyze verify /etc/systemd/system/linux-maa-webui.service` passed; `systemctl status linux-maa-webui` shows the temporary unit registered and inactive; `systemctl is-enabled linux-maa-webui` returns `disabled`; `ss -H -ltn sport = :8000` returns no listener. `npm run build` in `frontend/` passed with the existing Vite large chunk warning.
- Confirmed (`2026-07-01_2153-manage-service-history`): After replacing scheduler SQLite persistence with text/JSONL history and adding separated process logging, `uv run python -m compileall -q src tests` passed and `uv run pytest -q` passed 31 tests.
- Confirmed (`2026-07-02_1933-config-sync-ui-schema`): After schedule stats refresh changes, `cd frontend && npm run build` passed with only the existing Vite large chunk warning. The active WebUI service on port 8000 served `/schedule/daily-test` with new frontend asset `/assets/index-X-BN5FN3.js`.
- Confirmed (`2026-07-02_1933-config-sync-ui-schema`): After LogPane details-button changes, `cd frontend && npm run build` passed with only the existing Vite large chunk warning. The active WebUI service served `/schedule/daily-test` with new frontend asset `/assets/index-CXQ_eVgV.js`; Playwright confirmed the details panel opens and header-side exact `info` text is gone.
- Confirmed (`2026-07-02_1933-config-sync-ui-schema`): After source-aware log translation, git-output grouping, translation-rule additions, and SSE reconnect full `log_entries` recovery, `uv run python -m compileall -q src tests`, targeted `uv run pytest tests/test_maa_logs.py tests/test_web_sse.py -q` (16 tests), and full `uv run pytest -q` (38 tests) passed. The temporary systemd WebUI service `linux-maa-webui` was restarted and `GET http://127.0.0.1:8000/api/schedules/current` returned idle state.
- Confirmed (`2026-07-02_2245-tools-page`): After tools page/API implementation, `uv run python -m compileall -q src tests`, `uv run pytest -q` (38 tests), and `cd frontend && npm run build` passed. The existing systemd WebUI service `linux-maa-webui` was restarted and remains active on `http://127.0.0.1:8000/`; `GET /api/tools` returned the `game-update` definition and default address `192.168.5.151:5555`. Playwright smoke for `/tools` at desktop `1440x1000` and mobile `390x844` found no horizontal overflow and confirmed the run button is visible.
- Confirmed (`2026-07-02_2245-tools-page`): After unifying tool logs with `MaaCliLogTranslator` and adding terminal redraw collapse, `uv run python -m compileall -q src tests`, `uv run pytest -q` (41 tests), `git diff --check`, and `cd frontend && npm run build` passed. The real tool run `a25656161db4` completed before restart, installed game version 160 on `192.168.5.152:5555`, and ended `succeeded` with return code 0. The WebUI service was then restarted; `GET /api/tools` returned idle current-run state and `/tools` served frontend asset `/assets/index-BTx02CfX.js`.
- Confirmed (`2026-07-02_2245-tools-page`): After renaming the process primitive to `linux_maa.process.run_streaming_process()`, `uv run python -m compileall -q src tests`, targeted `uv run pytest tests/test_backend_utilities.py tests/test_maa_logs.py -q` (23 tests), and full `uv run pytest -q` (41 tests) passed.
- Confirmed (`2026-07-02_2245-tools-page`): After making the game-update Python subprocess unbuffered and adding the stopping-state guard, `uv run python -m compileall -q src tests`, `uv run pytest -q` (43 tests), `cd frontend && npm run build`, and `git diff --check` passed. The frontend build still reports the existing Vite >500 kB chunk warning. The `linux-maa-webui` service was restarted and `GET /api/tools` returned idle state.
- Confirmed (`2026-07-03_0105-audit-log-module`): After extracting WebUI-visible logs to `linux_maa.logs`, wiring maintenance and schedule scripts into the shared log buffer, and updating docs, `uv run pytest -q` passed 45 tests, `cd frontend && npm run build` passed with only the existing Vite >500 kB chunk warning, and `git diff --check` passed. The active `linux-maa-webui` systemd service was restarted; after the normal restart window, it was active on port 8000 and `GET /api/tools` / `GET /api/maintenance/current` returned successfully.
