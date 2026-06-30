# Session `2026-06-30_1752-maa-cli-sequential-analysis`

## Task

User asked for architecture analysis before changing runner behavior: what differs in `maa-cli` source between running a full custom task sequence once and running one child task only after the previous one completes.

## Sources Read

- Local project runner: `src/linux_maa/maa/runner.py`.
- Local runtime env: `src/linux_maa/maa/runtime.py`.
- Local direction docs: `docs/architecture-direction.md`, local mirrored CLI docs.
- Cloned current upstream `maa-cli` main into `scratch/maa-cli-src`, commit `503d6ce`.
- Local installed runtime reports `maa-cli v0.7.5`, `MaaCore v6.13.0`.

## Findings

- Confirmed: In upstream `maa-cli` main `crates/maa-cli/src/run/mod.rs`, `maa run <task>` calls `run_custom()`, parses the custom task into one `TaskConfig`, creates one MaaCore `Assistant`, appends every active `TaskConfig.tasks` entry through `asst.append_task(...)`, initializes one summary object, connects once, calls `asst.start()` once, then waits until `asst.running()` is false and calls `asst.stop()`.
- Confirmed: In that model, all child tasks in one custom task file share the same assistant instance, same callback object, same connection lifecycle, same resource load, same summary object, and one process-level `MAA_CORE_ERRORED` flag.
- Confirmed: Running each child task as a separate `maa run` process would repeat hot-update checks, profile loading, MaaCore setup, resource loading, assistant creation/destruction, callback/summary initialization, ADB connect, and start/stop for each child task.
- Confirmed: `TaskConfigTemplate::init()` performs task-level preprocessing over the whole custom task file before append: active variant resolution, global/default `client_type` inference, `startup`/`closedown` auto-prepend/append behavior, and relative `filename` normalization. Splitting into one-task generated files means the framework must preserve or replace any whole-file semantics it still wants.
- Likely: For typical one-child generated task files with explicit params, the main behavioral difference is lifecycle overhead and isolation, not a different MaaCore task algorithm. MaaCore still executes the same task type and params once appended.
- Likely: Separate invocations are better for outer orchestration because each child has an independent exit code, summary, log, timeout/retry boundary, and framework decision point. They are worse for overhead and may lose any accidental state/cached image/connection continuity within a single assistant instance.

## No Environment Changes

- No code/config/runtime behavior changed.
- A source clone was written under this session scratch directory only.

## Later Work In Same Session

- Confirmed: Implemented first log translation semantics in `src/linux_maa/maa/logs.py`. `MaaCliLogTranslator` recognizes info-level `TaskName Start`, `TaskName Completed`, `TaskName Error`, and `TaskName Stopped` lines, groups each child task in a text frame for the existing `<pre>` log UI, and records parsed per-child task results.
- Confirmed: `MaaRunState.to_dict()` now includes `task_results`; frontend `RunState` type has the matching optional field.
- Confirmed: `MaaRunManager` now owns one translator per run state and flushes it when a process exits or times out so unfinished task frames close as `unknown`.
- Confirmed: Added `tests/test_maa_logs.py`. `pytest` is not installed in this project, so direct function invocation was used with `uv run python`; all four test functions passed.
- Confirmed: `npm run build` in `frontend/` passed after the type update.
- Mistake: A restart command used a broad `pgrep -f "uv run linux-maa webui ..."` pattern, matched the current shell command, and killed itself with exit code 143. Safer pattern recorded in global lessons: use bracketed patterns such as `[u]v run ...`, filter out `$$`, or match a PID file/port owner.
- Active environment effect: WebUI was restarted and is currently running at `http://0.0.0.0:8000` from exec session `48633`, server PID `60357`. `GET /api/runs/current` returned `{"status":"idle","output":[]}` after restart.

## Log UI Rendering Update

- Confirmed: Replaced the pure-text child-task frame output with structured `log_entries`. Entries are either `line` or `task`; task entries include `messages`, and messages reserve fields for `tone`, rich `segments`, and `image`.
- Confirmed: Already translated task lifecycle lines no longer display the original raw maa-cli line. Recognized task-internal messages such as `ProductUnknown` are translated and omit `raw` from serialized message data.
- Confirmed: WebUI log panel now renders structured entries as timeline-style cards with a left timestamp column and status-colored task titles. Plain `output` remains as a fallback only.
- Confirmed: The runner no longer appends the full `maa run ...` command to the visible run log; it only appends a short run/attempt label.
- Confirmed: Validation after the render update: Python compile passed, manual parser tests passed, `npm run build` passed, and a Playwright page-load/screenshot check found no browser console/page errors. Screenshot: `.codex/conversations/2026-06-30_1752-maa-cli-sequential-analysis/scratch/log-pane-render-check.png`.
- Active environment effect update: WebUI was restarted again and is currently running at `http://0.0.0.0:8000` from exec session `91955`, server PID `6504`.

## Panel Rule And Border Refinement

- Confirmed: Added configurable backend panel-rule scaffolding through `MaaLogPanelRule`. The current default rule opens a panel on `TaskName Start` and closes it on `TaskName Completed/Error/Stopped`; future rules such as per-Fight-battle panels can be added as additional rules.
- Confirmed: Frontend task panels now use status-driven borders: running uses the theme color, succeeded uses the ordinary border, failed/stopped use warning color, unknown uses ordinary border.
- Confirmed: `FastestWayToScreencap <method> <cost>` now translates to include the method and shortest cost, e.g. `已选择截图方式: RawWithGzip, 最短耗时 203 ms`, with structured text segments for future colored rendering.
- Confirmed: Validation after the refinement: Python compile passed, manual parser tests passed, `npm run build` passed, API returned idle, and Playwright page-load/screenshot check found no browser console/page errors. Screenshot: `.codex/conversations/2026-06-30_1752-maa-cli-sequential-analysis/scratch/log-panel-status-border-check.png`.
- Active environment effect update: WebUI was restarted again and is currently running at `http://0.0.0.0:8000` from exec session `76798`, server PID `22306`.

## Main-Run Log Follow-Up

- Confirmed: Removed WebUI main-run timeout and retry concepts from `MaaRunManager`. Main-page manual runs are now single-shot; stopping a run sets final status `stopped` instead of relying on timeout/failure handling. The separate CLI command `linux-maa run-maa-task --attempts --timeout` remains unchanged.
- Confirmed: WebUI log filenames for new manual runs now use `runtime/maa/run-logs/<timestamp>-<task>-webui.log` instead of `...-webui-attempt-1.log`.
- Confirmed: Framework preprocessing messages are now added to structured `log_entries`. Current messages include resolved Fight stage and Infrast plan, for example `选择战斗关卡: 1-7` and `选择基建计划: 排班.json / 计划 #3`.
- Confirmed: Current WebUI process-channel behavior: `stdout` and `stderr` are merged with `stderr=subprocess.STDOUT`; this captures git output such as `From ...` and final `Summary`. The explicit `--log-file` is tailed separately and contains normal info-level maa-cli/MaaCore callback logs. Some process output is therefore visible in the UI without being present in the `runtime/maa/run-logs/*.log` file.
- Confirmed: Reduced the log card header gap by overriding the base card `gap-6` with `gap-0` and tightening header padding.
- Confirmed: Validation after this follow-up: preprocessing check produced both expected messages, Python compile passed, manual parser tests passed, `npm run build` passed, API returned idle, and Playwright page-load/screenshot check found no browser console/page errors. Screenshot: `.codex/conversations/2026-06-30_1752-maa-cli-sequential-analysis/scratch/log-header-preprocess-no-timeout-check.png`.
- Active environment effect update: WebUI was restarted again and is currently running at `http://0.0.0.0:8000` from exec session `86518`, server PID `46141`.
