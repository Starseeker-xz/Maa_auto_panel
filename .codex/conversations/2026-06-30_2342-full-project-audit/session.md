# Session 2026-06-30_2342-full-project-audit

## Task

User requested a complete, detailed audit of the current project after it reached a usable plateau:

- Audit backend first, every API and processing module, looking for coupling, duplicated implementations, and places that should be modularized.
- Write detailed Chinese backend audit results at repository root, including backend logic/module structure and issues found, then implement backend fixes.
- Audit frontend after backend, focusing on component reuse, duplicated logic, style stacking, inconsistent construction of similar pages, and other likely AI-generated issues.
- Write detailed Chinese frontend audit results at repository root, then implement frontend fixes.
- Compress/clean project history and old session scratch files, leaving a clean environment for future sessions.
- First step was planning only, after a broad code understanding pass.

## Baseline Observed

- Confirmed: repository path `/root/Linux_maa`; branch `main`; HEAD `6c7b851`; worktree was clean before saving this state.
- Confirmed: backend source is under `src/linux_maa/`, about 5999 lines.
- Confirmed: frontend source is under `frontend/src/`, about 4565 lines.
- Confirmed: tests are currently limited to four files under `tests/`.
- Confirmed: `uv run python -m compileall -q src tests` completed without output.
- Confirmed: `uv run pytest -q` passed 20 tests in about 0.74s.
- Confirmed: `cd frontend && npm run build` passed; Vite reported one large chunk warning (`index-*.js` about 751 kB, gzip about 239 kB).
- Confirmed: `.codex` occupies about 447M in the working tree, mostly old conversation scratch.
- Confirmed: `.codex/conversations/2026-06-29_2232-config-editing` occupies about 433M, due largely to a checked-out `scratch/maa-src` tree with large `.git` pack and ONNX/resource files.
- Confirmed: `git ls-files` shows many `.codex/conversations/**/scratch/*` files are tracked, plus gitlink entries for old upstream source checkouts under `.codex/conversations/**/scratch/`.
- Confirmed: `frontend/.codex` also exists and has tracked scratch screenshots.
- Confirmed: `.gitignore` currently ignores `runtime/`, `downloads/`, `frontend/node_modules/`, `frontend/dist/`, `TEMP/`, and config trash, but not `.codex/**/scratch/`, `frontend/.codex/`, or `debug/`.

## Initial Backend Findings

- Likely: `src/linux_maa/web/app.py` is an oversized API composition file. It instantiates all services and defines config/settings/maintenance/schedule/run routes in one place, with repeated exception-to-HTTP mapping.
- Confirmed: manual runs and scheduled runs already share `src/linux_maa/maa/process.py`, but still duplicate run state serialization, append/flush logging helpers, process status mutation, and idle response shapes in `maa/runner.py` and `scheduler/service.py`.
- Confirmed: helper implementations are duplicated across modules: slug normalization, atomic writes, dict-value guards, version parsing/comparison, and config path resolution patterns.
- Likely: several service classes return API-shaped dictionaries directly (`MaaStageService`, `MaaInfrastService`, maintenance info, scheduler responses), which couples domain logic to HTTP response shape.
- Confirmed: current tests cover config metadata, log translator behavior, scheduler policy, and final scheduler status semantics, but do not cover FastAPI route wiring, config write path safety, Stage/Infrast services, maintenance update info, or process orchestration with fake runners.

## Initial Frontend Findings

- Confirmed: `MainPage` is split into `TaskListPane`, `ConfigEditorPane`, and `LogPane`, but still owns much of task draft state, URL navigation, polling, and save/delete orchestration.
- Confirmed: `SchedulePage.tsx` is about 784 lines and mixes overview/detail routing, draft state, polling, entry editing, resize logic, settings panels, stats, and run controls.
- Confirmed: `SettingsPage.tsx` is about 817 lines and mixes settings data normalization, theme persistence, maintenance/update polling, and a large amount of field UI.
- Likely: editable list row patterns are duplicated between task item lists, schedule entry lists, and primitive array editors: rename state, blur-skip refs, hover controls, drag/drop insertion lines, and row styling.
- Likely: form field components exist locally inside `SettingsPage` but similar field/card/tooltip patterns are also embedded in schedule settings and JSON Forms renderers.
- Confirmed: frontend build currently passes, so frontend issues are primarily maintainability/duplication/layout-risk, not immediate build failure.

## Proposed Execution Plan

# 全项目审计与重构计划

## Summary

- Use session id `2026-06-30_2342-full-project-audit`; execution should continue from this session folder and append exact tests, edits, and cleanup actions to this file.
- Current baseline is usable: backend tests pass, frontend builds, and no immediate production-blocking failure was found during planning.
- Execution order should remain: backend audit -> backend root report -> backend fixes; frontend audit -> frontend root report -> frontend fixes; history/docs cleanup last.

## Backend Audit And Fixes

- Audit all of `src/linux_maa/`: CLI, ADB/game update, config/schema/task projection, MAA runtime/runner/process/logs/maintenance/stages/infrast, scheduler config/policy/store/service/time/scripts, storage/trash, FastAPI app.
- Add root `BACKEND_AUDIT.md` in Chinese. It should record the backend API list, module structure, data flow, run flow, config read/write flow, scheduler flow, log translation flow, discovered issues, and completed fixes.
- Prioritize structural fixes:
  - Split or modularize route groups from `web/app.py`, while preserving existing public paths.
  - Centralize exception-to-HTTP mapping and idle run response shape.
  - Factor shared manual/scheduled run state/log append/completion helpers where it reduces real duplication.
  - Consolidate repeated helpers for slug normalization, atomic write, version parsing, dict guards, and path resolution.
  - Separate domain/service return models from API response assembly where currently coupled.
- Keep public API compatibility unless a clear bug requires changing behavior.
- Add tests for config path/write safety, managed params projection, Stage/Infrast parsing, maintenance update-info parsing, manual/scheduled process helper behavior, and API error responses.

## Frontend Audit And Fixes

- Audit all of `frontend/src/`: App routing/sidebar, MainPage, SchedulePage, SettingsPage, LogPane, TaskListPane, ConfigEditorPane, JSON Forms renderer, PrimitiveArrayEditor, ProfileEditor, API/types/theme/task helpers, CSS.
- Add root `FRONTEND_AUDIT.md` in Chinese. It should record frontend page/component structure, state flow, API call flow, style system, reuse gaps, discovered issues, and completed fixes.
- Prioritize high-coupling files:
  - Extract reusable field/card/help-tooltip components out of `SettingsPage`.
  - Extract schedule overview/detail panes and schedule entry/task checklist behavior out of `SchedulePage`.
  - Reuse editable list row/rename/delete/drag patterns across task items, schedule entries, and primitive arrays.
  - Reuse polling/run-control/dirty-state helpers where they reduce duplication.
- Keep existing routes and user workflows unchanged: `/`, `/tasks/:taskConfig`, `/tasks/:taskConfig/items/:taskItemId`, `/schedule`, `/schedule/:scheduleId`, `/tools`, `/settings`.
- If layout changes are made, verify with Playwright screenshots/overflow checks on desktop and mobile.

## History And Repository Cleanup

- Add or update root `PROJECT_CLEANUP_AUDIT.md`, recording cleanup before/after sizes, retained/deleted rules, and compressed history sources.
- Compress `.codex`:
  - Keep `.codex/project-history.md`, `.codex/project-lessons.md`, `.codex/conversations/index.md`, current session file, and selected durable session summaries.
  - Remove/untrack old `.codex/conversations/**/scratch/*` raw logs, images, API payloads, upstream source checkouts, and gitlink entries after durable information is preserved.
  - Remove/untrack `frontend/.codex`.
- Update ignore rules to prevent future tracking of `.codex/**/scratch/`, `frontend/.codex/`, and likely `debug/`.
- Preserve durable findings from old sessions in `.codex/project-history.md`; do not keep raw data solely because it exists.

## Verification

- Backend: `uv run python -m compileall -q src tests`; `uv run pytest -q`.
- Frontend: `cd frontend && npm run build`.
- UI changes: start WebUI and use Playwright to inspect main page, schedule overview/detail, settings page at desktop and mobile sizes.
- Cleanup: run `git status --short` and `git ls-files .codex frontend/.codex debug TEMP runtime downloads frontend/dist frontend/node_modules` to confirm only intentional state/report files remain tracked.

## Assumptions

- Root audit reports should be Chinese: `BACKEND_AUDIT.md`, `FRONTEND_AUDIT.md`, `PROJECT_CLEANUP_AUDIT.md`.
- Large refactors are acceptable, but existing usable API paths, routes, config formats, and primary workflows should not be broken casually.
- Old scratch, screenshots, upstream source checkouts, and temporary API payloads are not long-term project assets once their durable conclusions have been summarized.

## Commands Already Run In Planning

- `date '+%Y-%m-%d_%H%M'` -> `2026-06-30_2342`
- `git status --short && git rev-parse --abbrev-ref HEAD && git rev-parse --short HEAD`
- `find src -maxdepth 4 -type f | sort`
- `find frontend/src -maxdepth 4 -type f | sort`
- `wc -l src/linux_maa/**/*.py src/linux_maa/*.py`
- `wc -l frontend/src/**/*.tsx frontend/src/**/*.ts frontend/src/*.tsx frontend/src/*.ts frontend/src/styles.css`
- `uv run python -m compileall -q src tests`
- `uv run pytest -q`
- `cd frontend && npm run build`
- `du -sh .codex .codex/conversations/*`
- `find .codex -type f -printf '%s %p\n' | sort -nr | head -40`
- `git ls-files` and targeted `git ls-files .codex ...` checks

## Context-Limit Handoff

This session stopped before implementation because context was approaching a risky length. A new session should load this file, then start execution from the proposed plan without redoing the full planning pass.

## Execution Continuation

- Confirmed: Continued execution in the same session id `2026-06-30_2342-full-project-audit`.
- Confirmed: Initial current baseline before edits:
  - `uv run python -m compileall -q src tests` passed.
  - `uv run pytest -q` passed 20 tests.
  - `cd frontend && npm run build` passed with the existing large Vite chunk warning.
- Confirmed: Current config differs from older project history: `config/linux-maa/settings.toml` has `framework.scheduler.enabled = true`.

## Backend Audit Execution

- Confirmed: Read all backend files under `src/linux_maa/`, all current tests, and current config files under `config/maa/` and `config/linux-maa/`.
- Confirmed: Added root `BACKEND_AUDIT.md` in Chinese with module structure, API list, data/run/config/scheduler flows, findings, fixes, remaining risks, and verification.
- Confirmed: Added shared backend helpers:
  - `src/linux_maa/utils.py` for slug/path/atomic-write/version/dict/bounded-int utilities.
  - `src/linux_maa/state.py` for idle/current-state response helpers.
- Confirmed: Split `src/linux_maa/web/app.py` into:
  - `web/services.py`
  - `web/responses.py`
  - `web/routes/configs.py`
  - `web/routes/settings.py`
  - `web/routes/maintenance.py`
  - `web/routes/maa.py`
  - `web/routes/schedules.py`
  - `web/routes/runs.py`
  - `web/routes/__init__.py`
- Confirmed: Replaced duplicate helper implementations in config manager/settings, scheduler config/models/scripts/service, maa runner/stages/infrast/maintenance, and game update manifest writing.
- Confirmed: Fixed scheduler `create_schedule()` precedence bug so an explicit `task_config` is preserved even when `list_kind("tasks")` is empty.
- Confirmed: Removed unused `seen` variable from `select_task_items()`.
- Confirmed: Added `tests/test_backend_utilities.py` covering config path traversal rejection, atomic text writes, version comparison, explicit task config schedule creation, and app OpenAPI path smoke.
- Confirmed: Backend verification after edits:
  - `uv run python -m compileall -q src tests` passed.
  - `uv run pytest -q` passed 25 tests.
  - OpenAPI smoke with a temporary repo root confirmed API paths are mounted.

## Session Mistakes

- Mistake: First FastAPI route smoke command iterated `app.routes` and directly accessed `route.path`, but this FastAPI version exposed an `_IncludedRouter` without that attribute.
- Outcome: Reran using `getattr(route, "path", "")`, then switched to `app.openapi()["paths"]`, which correctly verified mounted API paths.

## Frontend Audit Execution

- Confirmed: Read frontend entry/routing/API/types/theme/object-path/task-workspace/task schema helpers, custom JSON Forms renderers, shared components, Main/Schedule/Settings/Tools pages, main-page panes, schedule panes, and global CSS.
- Confirmed: Added root `FRONTEND_AUDIT.md` in Chinese with page/component structure, API/state flow, style observations, fixed issues, remaining risks, and build verification.
- Confirmed: Added shared frontend helpers/components:
  - `frontend/src/components/FormFields.tsx` for shared labels, help tooltip, text/number/select/checkbox/read-only/path fields.
  - `frontend/src/components/InsertionLine.tsx` for drag insertion markers.
  - `frontend/src/lib/usePolling.ts` for interval polling cleanup.
  - `frontend/src/pages/schedule/ScheduleLeftPane.tsx` for schedule identity/entry/task-list editing.
  - `frontend/src/pages/schedule/ScheduleDetailPanels.tsx` for schedule settings and stats panels.
- Confirmed: Removed duplicated form-field implementations from `SettingsPage` and `ProfileEditor`; JSON Forms and primitive array editors now reuse shared tooltip/insertion-line components where appropriate.
- Confirmed: Replaced repeated manual `setInterval` polling in `MainPage`, `SchedulePage`, and `SettingsPage` with `usePolling()`.
- Confirmed: Split `SchedulePage` from roughly 797 lines to roughly 382 lines by moving left/detail panes into `pages/schedule/`.
- Confirmed: Fixed a real schedule UI bug: after changing a schedule's bound task config, task checklist now immediately uses the newly read task config instead of stale `detail.task_config`.
- Confirmed: Fixed schedule detail refresh selection fallback when the previously selected entry no longer exists.
- Confirmed: Schedule entry id creation now prefers `crypto.randomUUID()` and checks existing ids before falling back.
- Confirmed: Frontend API error formatting now handles FastAPI `detail` arrays and project `validation.errors` instead of displaying raw JSON.
- Confirmed: Added `"tools"` to the `Page` type union.
- Confirmed: Frontend verification after edits:
  - `cd frontend && npm run build` passed.
  - The existing Vite large chunk warning remains.

## Frontend Session Mistakes

- Mistake: While replacing `TaskListPane`'s local insertion-line implementation, an empty trailing `function InsertionLine(...)` declaration was briefly left in the file.
- Outcome: Caught by immediate file inspection before build; removed the dangling declaration and then verified `npm run build` passed.

## Project History And Scratch Cleanup

- Confirmed: `.codex` was about `447M` before cleanup. The largest source was old `.codex/conversations/**/scratch/`, especially an upstream MAA source checkout with `.git/objects` and ONNX/resource files.
- Confirmed: Rewrote `.codex/project-history.md` into a compact current handoff and corrected the current scheduler fact: `config/linux-maa/settings.toml` has `framework.scheduler.enabled = true`.
- Confirmed: Updated `.codex/conversations/index.md`; current session is now described as audit execution rather than planning-only.
- Confirmed: Added root `PROJECT_CLEANUP_AUDIT.md` in Chinese with cleanup rules, before/after sizes, retained/deleted file classes, ignore rules, and process notes.
- Confirmed: Updated `.gitignore` to ignore:
  - `.codex/conversations/*/scratch/`
  - `frontend/.codex/`
  - `debug/`
- Confirmed: Deleted old `.codex/conversations/**/scratch/*`, `frontend/.codex/`, `TEMP/`, `debug/`, and Python `__pycache__/` directories.
- Confirmed: `.codex` was about `292K` immediately after cleanup.
- Confirmed: `find .codex/conversations -path '*/scratch/*' -type f` returned no files immediately after cleanup.
- Confirmed: `TEMP/`, `debug/`, and `frontend/.codex/` no longer exist.

## Cleanup Session Mistakes

- Mistake: First scratch cleanup command used nested `find -exec ... {} +`, which GNU find rejects because only one `{}` placeholder is allowed in that action form.
- Outcome: Re-ran cleanup using a `find ... -print0` shell loop and recorded the command-construction trap in `~/.codex/lessons.md`.

## Final Verification

- Confirmed: `uv run python -m compileall -q src tests` passed.
- Confirmed: `uv run pytest -q` passed with `25 passed`.
- Confirmed: `cd frontend && npm run build` passed with the existing Vite large chunk warning.
- Confirmed: Started Vite preview on port `4173` for UI smoke only, with Playwright route mocks for `/api/**` so no real backend scheduler was started.
- Confirmed: Playwright smoke checked `/tasks/test/items/startup`, `/schedule/daily-test`, and `/settings` at `1440x1000` and `390x844`.
- Confirmed: UI smoke passed and detected no horizontal overflow.
- Confirmed: UI smoke screenshots are stored under `.codex/conversations/2026-06-30_2342-full-project-audit/scratch/`.
- Confirmed: Final `.codex` size is about `936K` because current-session UI smoke screenshots are retained; old-session scratch remains empty (`find .codex/conversations -path '*/scratch/*' -type f ! -path '.codex/conversations/2026-06-30_2342-full-project-audit/scratch/*' | wc -l` returned `0`).
- Confirmed: Vite preview session was stopped after smoke verification.
- Confirmed: Final environment check found an older WebUI process on port `8000` (`uv run linux-maa webui --host 0.0.0.0 --port 8000`, PIDs `11009`/`11012`) from prior work, not from the UI smoke.
- Confirmed: Stopped the old WebUI process to leave a clean environment. `ss -ltnp | rg ':8000|:4173'` returned no listeners afterward.
