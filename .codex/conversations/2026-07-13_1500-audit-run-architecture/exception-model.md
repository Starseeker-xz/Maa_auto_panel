# Subagent `exception-model`

## Scope

- Parent session: `2026-07-13_1500-audit-run-architecture`.
- Implement the small application exception model and HTTP handlers.
- Translate explicit route-level builtin exception mappings without modifying `GenericRunManager`, process/command, run store, diagnostics, composition root, or the shared run-control router.

## Audit findings

- Most API groups repeated `ValueError -> 400`, `FileNotFoundError`/`KeyError -> 404`, and `RuntimeError -> 409` with route-local `HTTPException` construction.
- The shared `run_manager/router.py` maps manager lookup/control behavior and overlaps active run-manager work, so it was intentionally left unchanged.
- Coordinator resource conflicts can occur after a run has already been accepted and created; those must not be globally reinterpreted as synchronous HTTP 409 responses.
- `ConfigValidationFailure` already has route-specific structured 422 messages. Those paths remain intact; an app-level default handler now covers uncaught instances without discarding `result.to_dict()`.

## Changes

- Added `src/maa_auto_panel/errors.py` with five independent application exceptions: `InvalidRequest`, `ResourceNotFound`, `Conflict`, `CorruptState`, and `RuntimeUnavailable`. The module has no FastAPI dependency.
- Added `src/maa_auto_panel/web/exception_handlers.py` and registered handlers in `web/app.py`:
  - `InvalidRequest` -> 400
  - `ResourceNotFound` -> 404
  - `Conflict` -> 409
  - `CorruptState` -> 500 with server-side traceback logging and a non-sensitive client detail
  - `RuntimeUnavailable` -> 503
  - uncaught `ConfigValidationFailure` -> structured 422
- Converted explicit builtin-to-HTTP mappings in configs, schedules, settings, MAA query, maintenance, tools, run-start, and history routes into explicit builtin-to-application-exception boundary translations.
- Did not register handlers for Python builtins and did not modify the shared run-control router.
- Added `tests/test_web_exception_handlers.py` covering all mappings, corrupt-detail redaction, structured validation output, absence of builtin handlers, and a representative route boundary conversion.

## Verification

- `.venv/bin/python -m pytest -q tests/test_web_exception_handlers.py` -> `4 passed in 0.27s`.
- `.venv/bin/python -m compileall -q src/maa_auto_panel tests/test_web_exception_handlers.py` -> passed.
- `git diff --check` -> passed.
- Combined run with `tests/test_backend_utilities.py` -> 12 passed, 5 failed. All five failures are concurrent integration state outside this subtask: `RunStateStore.__init__` now requires `references`, while `web/services.py`, `ToolRunManager`, and some pre-existing tests still call it with only `runtime`.

## Session-only traps

- `uv run pytest` did not find pytest in this checkout, and `.venv/bin/pytest` has a stale `#!/root/Linux_maa/.venv/bin/python3` shebang. The reliable command is `.venv/bin/python -m pytest`; this is already covered by the existing project environment lesson about stale venv console-script shebangs.

## Future project trap to preserve

- Keep translating builtins only at a boundary where their semantics are known. Never register builtin exception handlers globally: `FileNotFoundError` may mean a requested resource is absent, a required runtime is unavailable, or an internal invariant is broken.
- Do not turn background coordinator contention into a synchronous 409 unless an explicit preflight happens before run record creation.
