# Session 2026-07-04_1115-review-cleanup

## Task

- Review backend and frontend in detail, clean dead code and compatibility imports, then commit the result.

## Session Notes

- Startup state files read before code inspection.
- Confirmed existing working tree only had this session directory before edits.
- Reviewed backend package-level re-export imports and replaced internal usages with imports from defining modules.
- Kept `linux_maa.tools.game` as an executable package; `_build_game_update_command()` still runs `python -m linux_maa.tools.game`, and `tools/game/__main__.py` imports implementation from `tools/game/update.py` directly.
- Frontend cleanup focused on TypeScript/Knip-confirmed unused exports and one unused `SchedulePage.refreshDetail()` helper.
- `uvx ruff` and `uvx vulture` downloaded temporary tool packages into the user/tool cache; no project dependency files were changed.
- `npx -y knip --production --reporter compact` reports only `@tailwindcss/vite` as unused, but it is used by `frontend/vite.config.ts`; kept it.

## Verification

- `uvx ruff check src tests` — passed.
- `uvx vulture src tests --min-confidence 80` — passed with no findings.
- `uv run python -m compileall -q src tests` — passed.
- `npx tsc --noEmit --noUnusedLocals --noUnusedParameters --pretty false` — passed.
- `uv run pytest -q` — 50 passed.
- `npm run build` — passed; existing Vite chunk-size warning remains.
- `uv run python -m linux_maa.tools.game --help` — passed, confirms the package remains executable through `python -m`.
- `systemctl restart linux-maa-webui.service` — passed; service active with PID 26857, listening on `0.0.0.0:8000`, and `curl http://127.0.0.1:8000/api/settings` returned OK.

## Environment Effects

- Active: `linux-maa-webui.service` was restarted in this session and remains active on port 8000.
