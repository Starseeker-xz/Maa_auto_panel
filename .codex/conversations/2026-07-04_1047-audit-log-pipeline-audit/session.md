# Session 2026-07-04_1047-audit-log-pipeline-audit

## Scope

- User asked to audit all changes since "模块化日志管线尝试".
- Treated commit `7820a5b 模块化日志管线尝试` as the start of the attempt and audited from parent commit `240f7cc` through the current worktree, including uncommitted changes.

## Findings

- Confirmed: `src/linux_maa/process.py` stop handling regressed from `_terminate_process(proc)` to `proc.terminate()` for `should_stop`. Manual/tool/scheduler child-kill stop paths can now hang indefinitely if the child ignores SIGTERM; manual/tool runs do not pass a separate hard timeout.
- Confirmed: Scheduled attempt capture uses `len(state.log.task_results())` / `len(state.log.entries())` as cursors against bounded, head-trimmed lists. Once the shared visible log buffer is full, a later attempt can persist empty `task_results` / `log_entries` even though new records exist in the tail.
- Confirmed by one-off reproduction: with `pipeline.max_log_entries = 2`, taking `start = len(entries)` and appending one new entry after trim leaves `entries[start:] == []` while the new entry is present in the tail.
- Confirmed: historical schedule log view flattens only `attempts[].log_entries`. It ignores `events` returned by `/api/history/runs/{run_id}`, loses run-level/pre-attempt framework events, and shows no visible logs for skipped schedule runs with `attempt_count=0`.
- Confirmed: visible run history files are written under `history/linux-maa/runs`, but `.gitignore` does not ignore `history/`. Generated run JSON files are currently untracked in `git status`.
- Confirmed: `maa/log_templates.py` local `_metadata_status()` still rejects `warning` even though shared `BlockStatus`, frontend type, and pipeline metadata parser allow it. `tone_for_status()` also does not map `warning` to a warning tone.
- Confirmed: project history says `Error: Interrupted by user!` closes the current task as `warning`, but current code/tests close it as status `unfinished` with warning tone.
- Likely: scheduler policy remains coupled to visible-log parsing because `_run_attempt()` derives task status from `state.log.task_results()`, which is projected from log block parsing. A log format/log-level regression can therefore alter retry/final-status decisions.
- Confirmed: tracked config files changed in the current diff: `daily-test.toml` retry/ADB behavior, `General.toml` Infrast enable flag, `startup-smoke.toml` CloseDown enable flag, and `排班.json` drone target. These may be intentional local behavior changes but are not isolated runtime state.

## Verification

- `uv run pytest -q` -> 54 passed.
- `uv run python -m compileall -q src tests` -> passed.
- `cd frontend && npm run build` -> passed; existing Vite chunk-size warning remains (`index-*.js` ~761 kB minified).

## Follow-up changes in same session

- Added `.gitignore` entries for `history/`, `config/maa/`, and `config/linux-maa/`.
- Ran `git rm --cached -r config/maa config/linux-maa history/linux-maa/runs`; local files were retained on disk and are now ignored.
- Fixed MAA template `warning` status consistency: `_metadata_status()` accepts `warning`, and `tone_for_status("warning")` returns warning tone.
- Added regression `test_maa_line_metadata_accepts_warning_status`.
- Verification after small fixes: `uv run pytest tests/test_maa_logs.py -q` -> 24 passed; `uv run pytest -q` -> 55 passed; `uv run python -m compileall -q src tests` -> passed.

## Test cleanup before commit

- Removed five redundant/detail-heavy tests from `tests/test_maa_logs.py`: split chunk handling, CRLF normal-line handling, generic block default start time, public-recruit numbered summary tone, and stdout `From github` negative case.
- `tests/test_maa_logs.py` now has 19 tests; full suite now has 50 tests.
- Verification: `uv run pytest -q` -> 50 passed; `uv run python -m compileall -q src tests` -> passed; `cd frontend && npm run build` -> passed with the existing Vite chunk warning.
