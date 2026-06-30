# Session 2026-06-30_2056-scheduled-execution

## Task

- User asked to audit and simplify architecture/code/style coupling before implementing the scheduled execution feature described in `TEMP/定时执行功能.md`.
- The scheduled execution feature is the core business; the existing main page is primarily a task config editor/manual test runner.

## Startup State

- Confirmed: Global lessons, global memory index, project history, project lessons, and project conversation index were read at session start.
- Confirmed: Relevant durable prior state says `retry_even_success` metadata exists, but scheduling/retry orchestration, persistent run records, and scheduler UI are not implemented yet.
- Confirmed: `git status --short` was clean at session start.

## Temporary Assumptions

- Favor architecture cleanup and deletion of obsolete coupling where it reduces risk before adding the scheduler.
- Keep session-only scratch data under `.codex/conversations/2026-06-30_2056-scheduled-execution/scratch/`.

## Audit Notes

- Confirmed: `frontend/src/pages/SchedulePage.tsx` is only a placeholder.
- Confirmed: `src/linux_maa/web/app.py` is a single route-registration file and will become difficult to maintain if schedule routes are added inline without service boundaries.
- Confirmed: `src/linux_maa/maa/runner.py` currently mixes generated config preparation, subprocess management, in-memory active-run state, log translation, and manual WebUI run behavior. Scheduled execution should reuse a lower-level process/config generation layer instead of expanding `MaaRunManager`.
- Confirmed: `FrameworkSettingsManager` already resolves user/client/backend timezone, but there is no reusable server-game-day module. The scheduler needs a separate time-domain module that can compute CN server-day reset semantics.
- Confirmed: settings-page field helpers are embedded inside `SettingsPage.tsx`; schedule per-config profile editing will need similar controls, so those helpers should be extracted or duplicated only minimally.
- Confirmed: `frontend/src/pages/main/LogPane.tsx` is generic enough to reuse for scheduled logs if its title/empty state can be parameterized.
- Confirmed: project history/docs say default profile touch mode is `ADB`, but current tracked `config/maa/profiles/default.toml` has `touch_mode = "MaaTouch"`. This session will not silently change it as part of scheduler implementation.
- Mistake: an initial `rg` audit search scanned `frontend/node_modules/` and generated very large output. Project lesson was added.

## Tests Run

- `uv run pytest`: passed 11 tests after adding scheduler policy/game-day tests.
- `uv run pytest`: passed 16 tests after fixing retry state, Summary grouping, `txwy` validation, and Infrast plan-name logging.
- `uv run pytest`: passed 18 tests after adding duplicate task-type labeling and initial skip-reason selection tests.
- `uv run pytest`: passed 20 tests after fixing scheduled run final-status semantics for current-run successes when daily thresholds are still unmet.
- `uv run python -c "from linux_maa.web.app import create_app; app = create_app(); print(app.title)"`: passed and printed `Linux MAA WebUI`.
- `npm run build` in `frontend/`: passed. Vite reported the existing large chunk warning for the main bundle.
- `npm run build` in `frontend/`: passed again after moving `小工具` to top-level `/tools` and fixing sidebar text alignment.
- `npm run build` in `frontend/`: passed again after adding optional `task_id`/`source_name` fields to frontend log types.
- `npm run build` in `frontend/`: passed after final-status fix.
- `curl -fsS http://127.0.0.1:8000/api/schedules`: passed after server startup; returned disabled scheduler status and `daily-test`.
- `curl -fsS http://127.0.0.1:8000/api/schedules/daily-test`: passed and returned schedule detail with Bilibili game-day order 22:00 -> 04:00 -> 08:00 -> 16:00.
- `curl -fsS http://127.0.0.1:8000/api/schedules/current`: passed and returned idle state.
- Playwright screenshots/overflow checks:
  - `scratch/overview-desktop.png`
  - `scratch/detail-desktop.png`
  - `scratch/detail-mobile.png`
  All reported zero horizontal overflow and no page errors.
- Playwright schedule UI checks after user-reported retry/log/sidebar issues:
  - `scratch/ui-checks/tools-top-level-desktop.png`
  - `scratch/ui-checks/schedule-detail-after-tools-fix.png`
  Confirmed: top-level nav order includes `主界面`, `定时执行`, schedule child `daily-test`, top-level `小工具`, and `设置`; `小工具` is not inside the schedule child container; main/settings/tools button `text-align` is left; schedule rows are two-line with only a `time` input and no name input in the normal state.
- Playwright schedule-left compact/resizer check:
  - `scratch/ui-checks/schedule-compact-resizer-desktop.png`
  Confirmed: schedule time input width is 108px; active schedule row height is 70px; the horizontal separator exists and dragging it changed the time-table section height from about 321px to 391px.

## Latest Run Audit

- Confirmed: Latest stopped scheduled run in `runtime/linux-maa/scheduler.sqlite3` was run `2d8a4d64bddc` for `daily-test` entry `t1600` / `中途切换`, status `stopped`, attempts 1-4.
- Confirmed: Attempt 3 generated config actually ran `StartUp -> Recruit -> CloseDown`, but persisted `task_ids` were `StartUp, CloseDown, Recruit`. Root cause was retry policy returning rerun-on-retry tasks before failed causes instead of preserving original task config order.
- Confirmed: Attempt 4 incorrectly selected `Award`, `Infrast`, and `Fight` again after they had succeeded in earlier attempts. Root cause was retry policy treating important unlimited tasks absent from the immediately previous retry attempt as `missing`, without remembering successes already achieved during the current scheduled run.
- Confirmed: Daily stats update previously counted every selected retry task name, including tasks whose per-attempt status was `missing`; fixed to update stats only for tasks with a non-`missing` result.
- Confirmed: Summary tail lines from maa-cli were stored as one line entry each; fixed by adding a structured `summary` log entry that groups the tail block and marks failed summaries with danger tone.
- Confirmed: Active run `e366017e6237` for `daily-test` / `t1600` generated only one `Fight`, `刷理智`. This was not a duplicate-type overwrite: `General.toml` and the schedule entry both contain `剿灭` and `刷理智`, but `daily_task_stats` for game day `2026-07-01` shows `剿灭` already had `successes=1` and its policy is `unlimited_runs=false`, `min_daily_successes=1`, so initial selection skipped it as already satisfied.
- Confirmed: Attempt 2 of stopped run `2d8a4d64bddc` generated both Fight tasks and the maa-cli log contains two consecutive `Fight Start/Completed` blocks. The remaining defect was observability: both blocks were labeled only as `Fight`, making duplicate task types hard to distinguish.
- Implemented: Scheduled attempts now seed `MaaCliLogTranslator` with the expected task sequence. Duplicate source task types can be displayed and recorded as their configured task names, with `task_id` and `source_name` preserved for status mapping.
- Implemented: Initial task selection now returns skip reasons. Scheduler logs enabled-but-skipped subtasks, e.g. `跳过子任务: 剿灭，原因: 今日成功次数已满足 1/1`.
- Confirmed: Run `e366017e6237` had attempt 1 failed on Recruit and attempt 2 succeeded with return code 0, but the run was marked `failed` because `_final_status` required all daily thresholds to already be fully met. At that moment `自动公招` was `1/2` and `刷理智` was `2/3`, even though both had succeeded in the current run.
- Implemented: `_final_status` now treats important finite-threshold tasks as satisfied for the current run when they have succeeded during that run, even if their daily goal still needs later scheduled entries. Unlimited important tasks still require current-run success.
- Updated: Corrected persisted run `e366017e6237` from `failed` to `succeeded` with summary `final_status=succeeded`.

## Local Environment Changes

- Created this session directory and scratch directory.
- Built `frontend/dist` via `npm run build`; directory is ignored by git.
- `uv run python ... create_app()` and the WebUI startup created ignored runtime DB `runtime/linux-maa/scheduler.sqlite3`.
- Created tracked schedule config `config/linux-maa/schedules/daily-test.toml`; it is disabled by default.
- Started earlier WebUI on `http://0.0.0.0:8000` from exec session `5763`; user later manually stopped/killed the latest run/server state.
- Restarted WebUI on `http://0.0.0.0:8000` from exec session `6856`; uvicorn server PID was `42815`.
- Stopped session `6856` after run completion and restarted WebUI on `http://0.0.0.0:8000` from exec session `16939`; uvicorn server PID is `11012`.

## Mistakes / Discarded Paths

- Initial `rg` audit search scanned `frontend/node_modules/` and mirrored docs; added project lesson to exclude those paths in broad searches.
- First Playwright `node -e` command used JavaScript template literals inside a double-quoted shell string, so bash treated backticks as command substitution. Reran with single-quoted Node code and string concatenation.
- Tried bare `python` for a quick JSON check, but this environment does not have `python` on PATH. Use `uv run python` in this repo.
- Initially placed `小工具` under the expandable `定时执行` child list. User clarified it is a sidebar page at the same level as `定时执行`; moved it to top-level route `/tools`.
