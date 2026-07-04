# Session 2026-07-04_0341-log-template-framework

## Task
- Refactor log template pipeline into generic block rule framework.

## Notes
- Session initialized.
- Implemented `logs/pipeline.py` as source defaults + `BlockDefinition` rules with per-source `active_blocks`, `LogLineInput` metadata, fallback line translation, close reasons `matched_end|superseded|passive_boundary|flush`, and pipeline projections.
- Replaced MAA `MaaLogTemplate` class with `register_maa_log_sources()` and block hooks for task lifecycle, stdout run summary, stdout resource update, and stderr fetch diagnostics.
- Removed public `append_event`/`EventLogTemplate` usage. Framework events now use `append(..., source="framework:event", metadata={"time": ..., "tone": ...})`.
- Frontend `MaaLogEntry.kind` is now `string`; task/log block status uses generic `MaaBlockStatus` including `default` and `warning`.
- Session-specific mistake: during the first superseded-task test, task close consumed the next start line's `TaskEventMatch`, leaving the old task as `running`. Fixed `_on_task_close()` to use `TaskEventMatch` only for `reason == "matched_end"`.

## Verification
- `uv run pytest tests/test_maa_logs.py -q` -> 21 passed.
- `uv run pytest -q` -> 51 passed.
- `uv run python -m compileall -q src tests` -> passed.
- `cd frontend && npm run build` -> passed; existing Vite large chunk warning remains.
