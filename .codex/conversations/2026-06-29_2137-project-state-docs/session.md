# Session 2026-06-29_2137-project-state-docs

## Task

User asked to fully inspect the current project state, then clean up and supplement project history and documentation.

## Startup

- Confirmed: Repository path is `/root/Linux_maa`.
- Confirmed: Read `~/.codex/lessons.md` and `~/.codex/memories/index.md`.
- Confirmed: Detailed global memory was not loaded because the current task is project-local documentation/state maintenance.
- Confirmed: Read existing project state files when present: `.codex/project-history.md`, `.codex/project-lessons.md`, and `.codex/conversations/index.md`.

## Work Log

- Created session folder `.codex/conversations/2026-06-29_2137-project-state-docs/`.
- Inspected git status, README/docs, Python CLI/runtime/WebUI code, frontend package/page structure, managed MAA config, active runtime process, and tool versions.
- Rewrote `.codex/project-history.md` into a concise current handoff with source session ids and updated facts.
- Updated `README.md`, `docs/README.md`, `docs/maa-runtime.md`, and `docs/architecture-direction.md` to match the current runtime/config/WebUI/frontend state.
- Added project-history and project-lessons guidance that descriptive files are active handoff state and should be checked whenever code/config/runtime/frontend behavior changes.
- Added project-stage guidance: the project is early-stage, so redesigns/upgrades should prioritize clean architecture/environment improvements and delete obsolete functionality instead of keeping fallback code by default.

## Verification

- `uv run python -m compileall src`: passed.
- `npm run build` in `frontend/`: passed; updated ignored `frontend/dist/` build output.
- `curl -fsS http://127.0.0.1:8000/api/configs`: passed against the already-running WebUI process.
- `scripts/maa-env maa run startup-smoke --batch --profile default --dry-run`: passed and reported StartUp as unstarted in dry-run summary.

## Observations

- Confirmed: Active WebUI process was already running on port `8000` before documentation edits (`uv run linux-maa webui --host 0.0.0.0 --port 8000`, child pid `58210`).
- Confirmed: No business code was edited in this documentation/state cleanup.
