# Session: 2026-07-03_1926-project-review

## Task
Full project review and compatibility cleanup — remove outdated compatibility shims and dead code.

## Findings

### Dead compatibility re-export modules (0 imports anywhere)
- `src/linux_maa/adb.py` → re-exports `ADBDevice` from `android.adb`
- `src/linux_maa/constants.py` → re-exports from `settings`
- `src/linux_maa/game_update.py` → re-exports from `game.update`
- `src/linux_maa/maa_runner.py` → re-exports from `maa.runner` + `maa.runtime`

### Dead compatibility directory
- `src/linux_maa/maa/logs/` — contained only `__init__.py` with `MaaCliLogTranslator` alias + stale `__pycache__` from before the module was moved to `linux_maa.logs`. Zero imports.

### Dead compatibility aliases in active files
- `src/linux_maa/logs/records.py`: `MaaLogMessage`, `MaaSummaryLogRecord`, `MaaTaskLogRecord` — never imported in src or tests.
- `src/linux_maa/maa/logs/__init__.py`: `MaaCliLogTranslator = RunLogTranslator` — zero imports.

### Dead frontend function
- `frontend/src/lib/logs.ts`: `translateLogLine()` was a no-op pass-through, never called. STATIC_LABELS retained — used by 4 files.

## Actions

1. Deleted `src/linux_maa/adb.py`, `constants.py`, `game_update.py`, `maa_runner.py`
2. Deleted entire `src/linux_maa/maa/logs/` directory
3. Removed `MaaLogMessage`, `MaaSummaryLogRecord`, `MaaTaskLogRecord` aliases from `logs/records.py`
4. Removed dead `translateLogLine` from `frontend/src/lib/logs.ts`, kept `STATUS_LABELS`
5. Cleaned all `__pycache__` directories
6. Updated `BACKEND_AUDIT.md`, `project-history.md`, `conversations/index.md`

## Verification
- `uv run python -m compileall -q src tests`: clean
- `uv run pytest -q`: 45 passed
- `npm run build`: ✓ built in 2.23s
