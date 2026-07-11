# Session 2026-07-10_0004-complete-rename-maa-auto-panel

## Task

- Complete project rename/refactor from Linux MAA / `linux_maa` / `linux-maa` to Maa Auto Panel.
- UI/display name should be `Maa Auto Panel`, not `Maa_auto_panel`.
- Extract frontend title/branding instead of hardcoding it in the app shell.

## Startup

- Loaded global lessons, memory index, project history, project lessons, and project conversation index.
- Session scratch directory: `.codex/conversations/2026-07-10_0004-complete-rename-maa-auto-panel/scratch/`.

## Initial decisions

- Display title: `Maa Auto Panel`.
- Python import package: `maa_auto_panel`.
- CLI/package slug and runtime directories: `maa-auto-panel`.
- No compatibility aliases unless tests or runtime constraints expose a concrete need; project is still early and user explicitly requested a full refactor.

## Updated Direction

- User clarified that persistent runtime areas should be generic framework-oriented, not product-name-oriented.
- Final boundary:
  - Product/app display: `Maa Auto Panel`.
  - Python package and CLI: `maa_auto_panel`, `maa-auto-panel`.
  - Framework runtime directories: `config/framework`, `state/framework`, `debug/framework`, `history/framework`.
  - Framework task metadata namespace: `framework`.
  - Framework runtime placeholders/schema extensions: `__framework_runtime__:*`, `__framework_stage__:current_last`, `x-frameworkManaged`.

## Changes

- Moved backend package from `src/linux_maa/` to `src/maa_auto_panel/` and updated imports/tests/entry points.
- Changed project package and CLI from `linux-maa` to `maa-auto-panel`.
- Extracted frontend title into `frontend/src/lib/branding.ts` and backend title into `src/maa_auto_panel/branding.py`; UI title is `Maa Auto Panel`.
- Migrated local runtime directories:
  - `config/maa-auto-panel` -> `config/framework`
  - `state/maa-auto-panel` -> `state/framework`
  - `debug/maa-auto-panel` -> `debug/framework`
  - `history/maa-auto-panel` -> `history/framework`
- Replaced task metadata/config UI namespace from `maa_auto_panel` to `framework`.
- Replaced managed schema key from `x-maaAutoPanelManaged` to `x-frameworkManaged`.
- Replaced runtime placeholders from `__maa_auto_panel_runtime__:*` / `__maa_auto_panel_stage__:*` to `__framework_runtime__:*` / `__framework_stage__:*`.
- Migrated systemd unit from `/etc/systemd/system/linux-maa-webui.service` to `/etc/systemd/system/maa-auto-panel-webui.service`; command is now `uv run maa-auto-panel webui --host 0.0.0.0 --port 8000`.
- Renamed the local repository root from `/root/Linux_maa` to `/root/Maa_auto_panel` and updated the systemd working directory.
- User renamed the GitHub repository to `Starseeker-xz/Maa_auto_panel`; updated `origin` to `git@github.com:Starseeker-xz/Maa_auto_panel.git`.

## Verification

- `uvx ruff check src tests`: passed.
- `uv run python -m compileall -q src tests`: passed.
- `uv run pytest -q`: 66 passed.
- `npm run build` in `frontend/`: passed; Vite emitted the existing large chunk warning.
- `uv run maa-auto-panel --help`: passed.
- `uv run python -m maa_auto_panel.tools.game --help`: passed.
- `git diff --check`: passed.
- Search over tracked source/docs/tests/frontend excluding `.codex`/runtime/debug found no old `linux_maa`, `linux-maa`, `Linux MAA`, old placeholder, old metadata, or old directory namespace except expected current package/CLI names.
- Search over local `config`, `state`, and `history` found no old `linux-*` or `maa_auto_panel` framework metadata/path strings.
- Restarted `maa-auto-panel-webui.service`; `/api/settings` returned `config/framework/settings.toml` and service is listening on `0.0.0.0:8000`.
- Verified the renamed GitHub repository over SSH with `git ls-remote --symref origin HEAD`; `HEAD` resolves to `main`.

## Mistakes

- A broad replacement over tests/docs changed imports like `from maa_auto_panel...` to `from framework...`. Fixed immediately by restoring package imports while keeping config metadata as `framework`.

## Environment Effects

- Active service: `maa-auto-panel-webui.service`, disabled but currently running on port 8000.
- Active service working directory: `/root/Maa_auto_panel`.
- Old service file `/etc/systemd/system/linux-maa-webui.service` was renamed to `/etc/systemd/system/maa-auto-panel-webui.service`.
- Local ignored runtime state moved to framework directories under `config/`, `state/`, `debug/`, and `history/`.
- `frontend/dist/` was refreshed by `npm run build`.
