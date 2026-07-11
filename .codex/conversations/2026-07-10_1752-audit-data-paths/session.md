# Session: audit data paths

- Session id: `2026-07-10_1752-audit-data-paths`
- Scope: audit all file persistence/path logic before containerization, with emphasis on consolidating mutable application data under `data/`.
- Current phase: path refactor and local data migration complete; service restored and verified.

## Design correction

- User clarified that download artifacts are not framework runtime dependencies and must not be classified as framework data merely because containers may persist them.
- Revised layout separates `data_root` (framework-owned/runtime-dependent data), `cache_root/downloads` (disposable cache), and an independent `/home/panel/.android` named volume (ADB client authorization keys).
- `data/home/.android` was rejected: persisting a generic HOME is too broad and conflates connector credentials with framework data.

## Implementation

- Added `ApplicationPaths`, `FrameworkPaths`, `CachePaths`, `MaaInstallation`, and `PathLayout` in `src/maa_auto_panel/paths.py`.
- `MaaRuntime` aggregates the separated path objects; mutable paths derive from `data_root`, downloads from `cache_root`, and frontend/schema assets from application root.
- Path precedence: explicit argument > `MAA_AUTO_PANEL_DATA_DIR`/`MAA_AUTO_PANEL_CACHE_DIR` > `<repo>/data`/`<repo>/cache`.
- Added CLI `webui --data-dir/--cache-dir`.
- Run history, diagnostics, config/trash display paths are now relative to data root. Existing `debug/...`, `history/...`, and `runtime/...` references remain portable after moving the root.
- Package manifests now store download-cache-relative paths and reject paths escaping the download directory.
- Updated `scripts/maa-env`, README, runtime docs, architecture docs, `.gitignore`, and container plan.

## Local migration performed

- Before migration: systemd service active, `/api/runs/current` idle.
- Dry-run identified six actions and wrote nothing.
- Stopped `maa-auto-panel-webui.service`, then moved legacy `config`, `state`, `history`, `debug`, and `runtime` to `data/`; moved `downloads` to `cache/downloads`.
- Normalized stale `/root/Linux_maa/downloads/...` manifest paths to cache-relative filenames.
- Replaced local config `$schema` repository-relative annotations with the schema `$id` URLs; removed the nonexistent framework settings schema annotation.
- Restarted systemd service. Verified config API, recent history detail, current idle state, `maa-cli v0.7.5`, `MaaCore v6.13.0`, and both cached APK paths.

## Verification

- `.venv/bin/python -m pytest -q`: 73 passed.
- `.venv/bin/python -m compileall -q src tests`: passed.
- `git diff --check`: passed.
- Isolated WebUI smoke test on port 18000 with explicit data/cache roots: API returned 200; process shut down after test.
- Ruff could not run because the current venv/project environment has no Ruff executable/module; no package was installed for this check.

## Session lessons / observed issues

- Mistake: introduced an unnecessary migration CLI, layout version, legacy detection, and compatibility framing even though the project is unpublished. Removed all of them after user correction; future pre-release structural changes should go directly to the final layout.
- Stopping the idle production service still reached systemd's 20-second timeout and required SIGKILL. Journal stopped at Uvicorn `Waiting for connections to close`; a WebUI SSE/EventSource connection is the likely immediate blocker. Idle meant no MAA run, not no HTTP connection/background thread. No run was active when the directory move began.

## Active environment effects

- Product data now lives under `/root/Maa_auto_panel/data` and disposable downloads under `/root/Maa_auto_panel/cache/downloads`.
- `maa-auto-panel-webui.service` is active again and serves the migrated layout.
