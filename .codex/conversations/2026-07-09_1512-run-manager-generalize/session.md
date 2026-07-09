# Session 2026-07-09_1512-run-manager-generalize

## Goal

Implement the accepted plan to remove domain-specific run fields from `run_manager/` and route task/MAA/scheduler details through generic metadata, artifacts, and attempt payloads.

## Notes

- User explicitly requested no compatibility or migration design.
- Existing worktree was already dirty before this session; do not revert unrelated changes.
- Session scratch directory: `.codex/conversations/2026-07-09_1512-run-manager-generalize/scratch/`

## Implementation Summary

- Removed task/MAA-specific fields from generic run state, manager decisions, and run history persistence.
- Replaced manager attempt task state with opaque `payload`; domains pass task lists via `{"task_ids": [...]}`.
- Added generic retry/run `metadata` and `artifacts`; MAA task results now go to retry metadata, generated config and MaaCore logs go to artifacts.
- Moved scheduler daily stats and trigger de-duplication from `RunStateStore` to `SchedulerStateStore`.
- Updated frontend run types and run details UI to read domain values from `metadata`/`artifacts`.
- Updated `RUN_MANAGER_REFACTOR_PLAN.md` to match the new boundary.

## Verification

- `uv run pytest -q` -> 66 passed.
- `uvx ruff check src tests` -> passed.
- `uv run python -m compileall -q src tests` -> passed.
- `cd frontend && npm run build` -> passed; Vite reported the existing >500 kB chunk warning.
- `git diff --check` -> passed.

## Commit

- `fd6b82f` — `Refactor run management lifecycle`
