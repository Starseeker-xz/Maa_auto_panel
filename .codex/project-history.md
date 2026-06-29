# Project History

## 2026-06-26_1620-maa-cli-framework-docs

- Confirmed: Repository path is `/root/Linux_maa`; git branch is `main`; current HEAD is `da108af` (`第一次提交, 仅包含一个自动下载更新组件`).
- Confirmed: Repository initially contains Python scripts for Bilibili Arknights APK/version/update support: `get_download_link.py`, `update_arknights.py`, and `diagnose_arknights_crash.py`.
- Confirmed: `pyproject.toml` declares project `linux-maa`, Python `>=3.12`, and dependencies `beautifulsoup4`, `hdiffpatch`, `lxml`, `requests`, `tqdm`.
- Confirmed: Current runtime is Debian 12 on CT `115`, IP `192.168.5.15/24`, default gateway `192.168.5.10`, kernel `6.8.12-9-pve`.
- Confirmed: `python3` is currently `3.11.2`; `uv` was not present in the shell during initial environment probing.
- Confirmed: Installed Debian package `ripgrep` (`rg`) during this session for faster repository/document search.
- Confirmed: `adb`, `nc`, `ping`, `curl`, and `rg` are available in CT `115` after the `ripgrep` install.
- Confirmed: CT `115` can reach target redroid CT `151` on `192.168.5.151:5555`.
- Confirmed: `adb connect 192.168.5.151:5555` succeeds; device reports `redroid14_x86_64`, Android `14`, SDK `34`, ABI `x86_64`, SELinux `Disabled`, `wm size` `1280x720`, density `240`.
- Confirmed: `com.hypergryph.arknights.bilibili` is installed on `192.168.5.151:5555`.
- Confirmed: `adb exec-out screencap -p` against `192.168.5.151:5555` produced a valid `1280x720` PNG with empty stderr. Scratch output: `.codex/conversations/2026-06-26_1620-maa-cli-framework-docs/scratch/adb/redroid151-screencap.png`.
- Confirmed: User wants this project to become a Docker-packaged framework that invokes `maa-cli`/MaaCore to automate Arknights on redroid, with automatic retry, fallback, finer scheduling, and better handling of unstable network/runtime failures than the Windows GUI.
- Confirmed: Target Android automation environment is CT `151`, redroid 14, IP `192.168.5.151`.
- Likely: Existing APK update code will become one feature of the larger framework, but should not be redesigned before the MAA/maa-cli documentation and integration model are understood.

## Next Promising Directions

- Mirror or otherwise preserve the relevant MAA Chinese documentation under `docs/maa-upstream/zh-cn/`.
- Read and summarize protocol/API, maa-cli usage, and Windows GUI user docs into project-local docs for future implementation.
- Inspect current scripts more fully before integrating them into any framework.
- Install/configure `maa-cli` and verify the exact active schema/profile keys, especially `device` vs `address`.

## 2026-06-26_1620-maa-cli-framework-docs Update Packaging

- Confirmed: Installed `uv` `0.11.24` under `/root/.local/bin` during this session.
- Confirmed: `uv python install 3.12` installed CPython `3.12.13`; `uv sync` created project virtualenv `.venv`.
- Confirmed: Existing game update script was repackaged into `src/linux_maa/` with command entry `linux-maa`.
- Confirmed: `linux-maa update-game` now fetches Bilibili game metadata, checks target ADB device version before downloading APK, reuses verified/unverified cache, can apply Bilibili incremental patches through `hdiffpatch`, falls back to full APK download, installs through ADB, and verifies installed version code.
- Confirmed: Legacy scripts `update_arknights.py` and `get_download_link.py` remain as compatibility wrappers.
- Confirmed: Smoke test `uv run linux-maa update-game` against `192.168.5.151:5555` exited without downloading/installing because remote version code and installed version code were both `160`.
- Confirmed: Smoke test `uv run linux-maa get-download-link` returned the current Bilibili APK URL.

## 2026-06-26_1620-maa-cli-framework-docs Product Requirements Clarification

- Confirmed: Long-term goal is a high-availability framework with Web UI, not just a command-line wrapper.
- Confirmed: Web UI should support GUI-like configuration authoring and task execution similar to MAA GUI.
- Confirmed: A unified, user-friendly visual editor for JSON/TOML-style configuration files is desired, covering framework config, MAA task config, MAA base/infrastructure config, and other config types. This is important but not the immediate implementation task.
- Confirmed: Framework should schedule and call `maa-cli`, not directly integrate MaaCore callbacks/API.
- Confirmed: Failure detection should be based on `maa-cli` logs/output.
- Confirmed: Retry/fallback policy must be granular by task and phase. Example desired behavior: for full task sequence `StartUp-A-B-C`, if `B` fails and `StartUp` is configured as always rerun before retry, retry should run `StartUp-B-C`; if `StartUp` then fails 3 consecutive times, send bot notification and pause 5 minutes before retry; if `C` fails but is marked non-critical, mark overall run complete and report accordingly.
- Confirmed: Framework should support extra operational functions: detect/update game APK, run miscellaneous MAA/maa-cli functions, run external scripts on schedules or before/after tasks, check/start/stop Android containers, update MaaCore/resources.
- Likely: Project needs a clear project structure and conventions before further implementation.
- Confirmed: Directional architecture recommendations were recorded in `docs/architecture-direction.md` for handoff.

## 2026-06-26_1702-setup-maa-cli-test

- Confirmed: User uploaded Windows-side MAA GUI exports to `TEMP/gui.json` and `TEMP/gui.new.json`; both have current profile `test`.
- Confirmed: `TEMP/gui.json` is the older flattened GUI format and contains durable connection values: ADB address `192.168.5.151:5555`, client `Bilibili`, GUI touch mode `maatouch`, and Windows ADB paths that should not be reused on Linux.
- Confirmed: `TEMP/gui.new.json` is a newer structured GUI/task export and current `test` queue includes StartUp, Award, Mall, disabled Infrast, Fight, UserDataUpdate, and Recruit.
- Confirmed: Infrast in the uploaded structured config references Windows path `D:\Game\MAA\排班.json`; do not enable it until the scheduling JSON is copied/migrated.
- Confirmed: Installed `maa-cli v0.7.5` to project-local `runtime/maa/bin/maa` via official install script with checksum verification.
- Confirmed: Installed `MaaCore v6.12.2`, libraries, bundled resources, and hot-update resources under project-local `runtime/maa/` using `scripts/maa-env` environment variables.
- Confirmed: Added `scripts/maa-env` to set `PATH`, `MAA_CONFIG_DIR`, `XDG_DATA_HOME`, `XDG_CACHE_HOME`, and `XDG_STATE_HOME` so `maa` uses only the project-local runtime.
- Confirmed: Initial live profile is `runtime/maa/config/profiles/default.toml`: ADB `192.168.5.151:5555`, `Bilibili`, `CompatPOSIXShell`, CPU OCR, `kill_adb_on_exit = false`. It first used `MaaTouch`, then was changed to `ADB` after logcat showed a MaaTouch crash.
- Confirmed: Initial live custom task is `runtime/maa/config/tasks/test.toml`, converted conservatively from uploaded `test`: StartUp, Award, Mall, Fight, Recruit; no Infrast yet.
- Confirmed: `scripts/maa-env maa run test --batch --dry-run` parsed the task successfully.
- Confirmed: First real `test` run completed with exit code 1. StartUp succeeded (`17:06:42 - 17:09:20`); Award, Mall, Fight, and Recruit all errored.
- Confirmed: Detailed MaaCore log for first real run is `runtime/maa/state/maa/debug/asst.log`; CLI-level log is `.codex/conversations/2026-06-26_1702-setup-maa-cli-test/scratch/maa-test.log`.
- Confirmed: Award entered the mail flow and repeatedly detected loading text `正在提交`; the saved Award failure screenshot was Android launcher/home, not a game screen. Screenshot copy: `.codex/conversations/2026-06-26_1702-setup-maa-cli-test/scratch/maa-award-error-raw.png`.
- Confirmed: Android logcat after the first real run showed `FATAL EXCEPTION: Thread-1` in `com.shxyke.MaaTouch.InputThread.run`, a MaaTouch `NullPointerException`. This supports using `touch_mode = "ADB"` on redroid CT `151` unless MaaTouch is fixed.
- Confirmed: After the first real run, Arknights process `com.hypergryph.arknights.bilibili` was still alive (`pid 3126`) and `:pushcore` was alive; Android foreground was launcher. This looked more like game backgrounding/input-layer failure than a full game process crash.
- Confirmed: ADB/ping to `192.168.5.151` were healthy; Android memory status was normal with total RAM about 16 GB and free RAM about 5.1 GB.
- Unknown: PVE CT `151` host-side status could not be checked because SSH to PVE host `192.168.5.55` from CT `115` failed with publickey/password denial.
- Likely: Mall/Fight/Recruit failures in the first real run were cascade failures because the game was backgrounded or no longer at a recognized in-game home state after Award failed.
- Next promising directions: isolate by running smaller single-task configs under `touch_mode = "ADB"`, especially StartUp-only and Award with `mail = false`; add explicit StartUp before later tasks in framework-level retry logic; copy/import the missing Infrast schedule JSON before enabling Infrast.
- Confirmed: `.gitignore` now ignores `runtime/` and `TEMP/`; `runtime/maa/` is live local state for Docker volume/runtime use, not source.
- Confirmed: Added runtime notes in `docs/maa-runtime.md`.
- Confirmed: Added first coarse recovery wrapper `linux-maa run-maa-task <task>` in `src/linux_maa/maa_runner.py`. It treats any maa-cli non-zero exit or timeout as failure, writes per-attempt logs under `runtime/maa/run-logs/`, reconnects ADB, optionally force-stops the game package, sends HOME, waits, and retries.
- Confirmed: `uv run python -m compileall src` and `uv run linux-maa run-maa-task --help` succeeded after adding the wrapper.
- Confirmed: User explicitly prefers framework behavior that ignores most individual instability causes and broadly retries/recovers rather than relying on detailed diagnosis.

## 2026-06-26_1702-setup-maa-cli-test Web UI Handoff

- Confirmed: Next major task should be scaffolding the Web UI framework, not continuing one-off `maa-cli` failure diagnosis.
- Confirmed: User is new to frontend development and wants detailed explanation of frontend choices and concepts.
- Likely: Best initial product shape is a small full-stack web app where Python remains the backend/control plane and the frontend is a separate TypeScript app built into static assets for Docker.
- Recommended: Use FastAPI for the backend API/WebSocket layer because the current project is Python/uv based and already contains Python orchestration code.
- Recommended: Use React + TypeScript + Vite for the frontend. This gives a common, well-documented component model, fast local dev server, and straightforward Docker build output without forcing a larger full-stack JavaScript framework.
- Recommended: Use Tailwind CSS plus shadcn/ui or lightweight headless/component primitives for the UI. The app is an operational dashboard, so prioritize dense, plain controls over landing-page styling.
- Recommended: Avoid Next.js initially. Its server/rendering model adds unnecessary concepts while the backend is already Python and the app is more of an internal control panel than a public website.
- Recommended: First Web UI slice should include dashboard/status, task run form, run attempt history/log tail, config file list/editor placeholder, and runtime health cards. Do not start with the full visual JSON/TOML editor.
- Recommended: Backend API should expose coarse domain actions first: list tasks, run task with retry policy, show active run state, stream logs, stop/cancel, run APK update, and return Android/maa runtime status.
- Recommended: Persist framework state in SQLite once needed; do not add Postgres/Redis before the first Web UI can run tasks and display logs.

## 2026-06-26_1727-webui-config-runner

- Confirmed: Added a minimal FastAPI WebUI served by `uv run linux-maa webui --host 0.0.0.0 --port 8000`.
- Confirmed: Active development WebUI is currently running on CT `115` at `http://192.168.5.15:8000/` from server process `25012`; source session id `2026-06-26_1727-webui-config-runner`.
- Confirmed: WebUI lists managed maa-cli config files from `runtime/maa/config/profiles/` and `runtime/maa/config/tasks/`, can show selected config content, start one active `maa run <task> --batch --profile <profile>` process, poll readable process output/status, and send a stop request.
- Confirmed: WebUI deliberately does not stream `runtime/maa/state/maa/debug/asst.log`; user rejected that because it is too low-level for normal UI output.
- Confirmed: `src/linux_maa` was reorganized into domain packages: `android/` for ADB operations, `game/` for APK update logic, `maa/` for maa-cli runtime/process control, `config/` for managed config indexing, and `web/` for the WebUI/API. Thin compatibility modules remain at `adb.py`, `constants.py`, `game_update.py`, and `maa_runner.py`.
- Confirmed: Added FastAPI/Uvicorn/Pydantic dependencies to `pyproject.toml` and updated `uv.lock`.
- Confirmed: Verification passed: `uv run python -m compileall src`, `uv run linux-maa --help`, `uv run linux-maa run-maa-task --help`, `scripts/maa-env maa run startup-smoke --batch --profile default --dry-run`, `GET /`, and `GET /api/configs`.
- Confirmed: A short WebUI run of `startup-smoke` with a 30 second timeout successfully exercised process start, polling, and timeout termination; this intentionally touched the Android/game runtime during testing.
- Likely: Normal maa-cli process output is sparse during long-running tasks. Better user-facing progress should be derived from higher-level parsing of maa-cli summaries and selected log events later, not raw `asst.log`.

## 2026-06-26_1727-webui-config-runner Direct MaaCore

- Confirmed: Experimental direct MaaCore ctypes runner exists at `.codex/conversations/2026-06-26_1727-webui-config-runner/scratch/maacore_direct_run.py`.
- Confirmed: `AsstLoadResource` must receive a base directory containing `resource/` (for example `runtime/maa/data/maa`), not `runtime/maa/data/maa/resource` itself.
- Confirmed: Direct MaaCore callbacks provide structured progress events. Observed event types include `ConnectionInfo`, `TaskChainStart`, `TaskChainCompleted`, `SubTaskError`, `TaskChainStopped`, and `Destroyed`.
- Confirmed: Direct full test run appended `StartUp`, `Award`, `Mall`, `Infrast`, `Fight`, and `Recruit`. Within 180 seconds, `StartUp` and `Award` completed; `Mall` emitted a `CreditShoppingTask` subtask error but completed; `Infrast` emitted internal `ProcessTask` subtask errors and was stopped by timeout; `Fight` and `Recruit` did not start.
- Confirmed: Copied uploaded base schedule from `TEMP/排班.json` to `runtime/maa/config/infrast/排班.json`.
- Confirmed: `runtime/maa/config/tasks/test.toml` Infrast params were hand-fixed to valid TOML with `filename = "排班.json"` and `plan_index = 3`; `preserve_tags` in Recruit is intentional and should not be rewritten to `first_tags`.
- Likely: WebUI should eventually consume MaaCore callback events directly or through a wrapper event model instead of showing raw MaaCore logs.

## 2026-06-26_1727-webui-config-runner WebUI Verbose Logs

- Confirmed: WebUI now runs maa-cli as `maa run <task> --batch --profile <profile> --log-file=<runtime/maa/run-logs/...> -v` and tails that maa-cli verbose log into the output panel.
- Confirmed: `--log-file` must use equals form with maa-cli (`--log-file=<path>`), not split argv form.
- Confirmed: `startup-smoke` Web API test returned visible progress lines: hot update, connected, screencap method, `StartUp Start`, `StartUp Completed`, `AllTasksCompleted`, summary, and exit code 0.
- Confirmed: Active WebUI was restarted after this change and is running on `http://192.168.5.15:8000/` from process `18365`.
- Confirmed: Added WebUI output granularity selector and API field `log_level`: `0` summary only, `1` normal (`-v`), `2` detailed (`-vv`), `3` trace (`-vvv`). After restart, active WebUI process is `27260`.

## 2026-06-26_1727-webui-config-runner GPU OCR Discovery

- Confirmed: maa-cli profile schema supports `[static_options] gpu_ocr = <integer>` and `cpu_ocr = false`; current default profile still uses `cpu_ocr = true`.
- Confirmed: This CT has GPU device nodes exposed (`/dev/dri/renderD128`, `/dev/nvidia0`) and `lspci` sees Intel Alder Lake-P iGPU plus NVIDIA RTX 2080 Ti.
- Likely: Windows GUI "GPU accelerated inference" is DirectML-oriented; Linux should require testing `gpu_ocr` with the available ONNX Runtime provider and container GPU drivers before enabling it.

## 2026-06-26_2030-separate-frontend

- Confirmed: The WebUI frontend has been split into an independent React + TypeScript + Vite app under `frontend/`.
- Confirmed: FastAPI now serves the built frontend from `frontend/dist` and returns a small fallback page if the frontend has not been built.
- Confirmed: Frontend layout now follows a three-column Web operational view: left task config selector and task-name list, center reserved config editor placeholder, right info-level maa-cli log panel.
- Confirmed: The task list currently displays only each task `name`; the backend still returns `index`, `type`, and `enabled` for future UI use.
- Confirmed: The `maa-cli` log translation layer exists at `src/linux_maa/maa/logs.py`; it currently returns log text unchanged.
- Confirmed: WebUI run requests use `log_level = 1`, corresponding to maa-cli `-v`/Info output.
- Confirmed: The desktop GUI's four top tabs should not be kept as always-visible Web header tabs; they have been moved into a left-top collapsible menu placeholder.
- Confirmed: The desktop GUI's green/red task-row background colors should not be copied; task success/failure will use a separate future status indicator.
- Confirmed: Visible attempts/timeout controls were removed from the left pane for now; the frontend still submits defaults `attempts = 1` and `timeout_seconds = 900`.
- Confirmed: UI direction was refined to a WinUI-like persistent sidebar, not a popover menu. Current sidebar pages are `主界面`, `定时执行`, and `设置`; settings sits at the bottom and non-main pages are blank placeholders for now.
- Confirmed: Profile selection should not be on the main page for now; it will be integrated into settings later. The frontend still submits profile `default` internally.
- Confirmed: Raw task config text should not be shown directly on the main page. A future toggle will switch the center pane between visual config editing and raw-file editing.
- Confirmed: Main task rows should include native checkboxes and per-task settings gear buttons.
- Confirmed: A Mantine experiment was removed. Frontend now uses shadcn-style local components in `frontend/src/components/ui/`, Radix primitives, Tailwind CSS v4, `@tailwindcss/vite`, and `tw-animate-css`.
- Confirmed: Sidebar behavior is now implemented as a local shadcn-style expandable/collapsible navigation rail: expanded width 224px (`w-56`), collapsed width 64px (`w-16`), icon-only when collapsed.
- Confirmed: Installed Debian `nodejs`/`npm` during the original frontend session, then upgraded Node with `n` to Node `v22.23.1` and npm `10.9.8` during session `2026-06-29_1929-shadcn-sidebar` so the current Tailwind v4/shadcn path builds cleanly.
- Confirmed: Frontend page code was split so `frontend/src/main.tsx` only mounts React, `frontend/src/App.tsx` owns the sidebar/page switch, pages live in `frontend/src/pages/`, and shared API/types/log helpers live in `frontend/src/lib/`.
- Confirmed: Frontend now uses React Router. Routes include `/`, `/tasks/:taskConfig`, `/tasks/:taskConfig/items/:itemIndex`, `/schedule`, and `/settings`; FastAPI SPA fallback serves these routes correctly.
- Confirmed: Main page's three columns are split into `frontend/src/pages/main/TaskListPane.tsx`, `ConfigEditorPane.tsx`, and `LogPane.tsx`.
- Confirmed: Subtask route identity was changed from list index to task item id. Current route shape is `/tasks/:taskConfig/items/:taskItemId`.
- Confirmed: Backend task item API now returns `id`. It uses explicit task `id` when present, otherwise generates a task-type plus content-hash id. These generated ids are stable across reorder but can change when task content changes; future editable framework configs should persist explicit per-task ids if edit-stable URLs are required.
- Confirmed: Active development WebUI was restarted after backend id changes and now runs from process `49415` on port `8000`.
- Confirmed: Editable MAA/framework config was moved out of ignored runtime state and now lives under `config/maa/`. `runtime/maa/` remains for downloaded Maa binaries/resources, state, logs, cache, and generated sanitized configs.
- Confirmed: Framework task metadata is stored under each task's `[tasks.linux_maa]` namespace. Current `config/maa/tasks/test.toml` has per-task `linux_maa.id` values: `startup`, `award`, `mall`, `infrast`, `fight`, and `recruit`.
- Confirmed: raw `maa-cli run <task>` rejects unknown `linux_maa` fields. The framework runner now generates temporary sanitized task JSON under `runtime/maa/generated-configs/<run-id>/tasks/` with `linux_maa` stripped before invoking maa-cli; non-task config dirs such as `profiles` and `infrast` are symlinked into that generated config root.
- Confirmed: Sanitized generated config dry-run succeeds for `test`; direct `scripts/maa-env maa list` still works. Use framework runner/WebUI for actual task runs when task files contain Linux MAA metadata.
- Confirmed: Active development WebUI was restarted after config split and now runs from process `58210` on port `8000`.
- Confirmed: Verification passed for `npm install`, `npm run build`, `uv run python -m compileall src`, `GET /`, `GET /assets/index-BCW4lrtK.js`, and `GET /api/configs/tasks/test`.
- Confirmed: Active development WebUI is running at `http://192.168.5.15:8000/` from process `55760`; source session id `2026-06-26_2030-separate-frontend`.
