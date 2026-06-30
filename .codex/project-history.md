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
  - `config/maa/tasks/award-no-mail.toml`
  - `config/maa/infrast/排班.json`
- Confirmed (`2026-06-29_2137-project-state-docs`): Default profile targets ADB serial `192.168.5.151:5555`, package `com.hypergryph.arknights.bilibili`, client `Bilibili`, connection config `CompatPOSIXShell`, touch mode `ADB`, and CPU OCR.
- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): `MaaTouch` caused a `NullPointerException` on redroid during earlier tests; keep `touch_mode = "ADB"` unless retesting/fixing MaaTouch intentionally.
- Confirmed (`2026-06-29_2232-config-editing`): Active development WebUI process was restarted on the normal port `8000` as `uv run linux-maa webui --host 0.0.0.0 --port 8000`.
- Confirmed (`2026-06-29_2137-project-state-docs`): Local frontend toolchain is Node `v22.23.1` and npm `10.9.8`.

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
- Confirmed (`2026-06-30_0014-task-editor-fixes`): Frontend task-config edits are local-only, including added configs/items, renames, deletes, ordering, enable toggles, metadata, and JSON Forms params. Running a task still uses the saved config file on disk; no frontend-to-backend config write/sync exists yet. Next stage is backend config save.
- Confirmed (`2026-06-30_0014-task-editor-fixes`): New local task-item defaults live in `frontend/src/config/task-item-defaults.json`; task workspace helpers for local config response, reindexing, renaming, delete, and enable toggles live in `frontend/src/lib/taskWorkspace.ts`.
- Confirmed (`2026-06-30_0014-task-editor-fixes`): JSON Forms renderer supports UI-only schema extensions `x-enabledWhen` and `x-disabledWhen`, plus titled `oneOf` enum values. These are frontend display/editing helpers and should not be serialized into maa-cli task params.
- Confirmed (`2026-06-29_2232-config-editing`): `docs/maa-cli/config_examples/tasks/full-current.toml` is a broad reference config for the current maa-cli task enum and MaaCore `integration.md` params. It passed the local maa-cli task JSON Schema validation.
- Confirmed (`2026-06-29_2232-config-editing`): MAA GUI candidate Fight stages are a GUI-layer `StagePlan`, not a MaaCore params schema feature. The GUI loads `gui/StageActivityV2.json` and `resource/tasks/tasks.json`, then serializes the first currently open stage into MaaCore's single `stage` param.
- Confirmed (`2026-06-29_2137-project-state-docs`): Sidebar pages are `主界面`, `定时执行`, and `设置`; schedule/settings are placeholders.
- Confirmed (`2026-06-26_2030-separate-frontend`): Profile selection is intentionally hidden from the main page for now; frontend submits profile `default`.

## Important Observations

- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): Target Android environment is redroid CT `151` at `192.168.5.151:5555`, Android 14 x86_64, screen `1280x720`, density `240`, SELinux disabled.
- Confirmed (`2026-06-26_1702-setup-maa-cli-test`): First full real `test` run had StartUp succeed, then Award/Mall/Fight/Recruit fail. Award entered mail flow and repeatedly detected loading text; saved failure screenshot showed Android launcher/home, suggesting app backgrounding/input-layer failure rather than a simple game process crash.
- Likely (`2026-06-26_1702-setup-maa-cli-test`): Mall/Fight/Recruit failures in that run were cascade failures after Award left the game in a bad or unrecognized state.
- Confirmed (`2026-06-26_1727-webui-config-runner`): Direct MaaCore ctypes experiment in session scratch showed structured callbacks are available, but project direction remains `maa-cli` wrapper first.
- Confirmed (`2026-06-26_1727-webui-config-runner`): MaaCore `AsstLoadResource` must receive a base directory containing `resource/`, such as `runtime/maa/data/maa`, not `runtime/maa/data/maa/resource`.
- Likely (`2026-06-26_1727-webui-config-runner`): Better user-facing progress should eventually come from selected `maa-cli` summary/log events or MaaCore callback-like parsing, not raw `asst.log`.
- Confirmed (`2026-06-26_1727-webui-config-runner`): WebUI deliberately does not stream low-level `runtime/maa/state/maa/debug/asst.log` into normal UI output.

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
- Build config editing incrementally: first task item enable/disable and selected task params, then schema-driven form editing, then raw editor toggle if needed.
- Add selected log parsing/translation in `src/linux_maa/maa/logs.py` so UI shows higher-level events without exposing raw MaaCore debug logs.
- Add status APIs for ADB/redroid, Maa runtime/resource versions, generated config paths, and recent run logs.
- Add targeted tests around `prepare_maa_cli_task`, metadata stripping, config resolution, task item id stability, and run manager process state.
