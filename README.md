# Maa Auto Panel

Automation panel for running MaaAssistantArknights against Android containers.

Current packaged features:

- `maa-auto-panel webui`: start the local FastAPI + React WebUI.
- WebUI tools: game update (download and install Bilibili Arknights APK) is available as an integrated third-party tool via `python -m maa_auto_panel.tools.game update-game`.
- WebUI scheduled execution: define per-schedule task/profile bindings, game-day-aware time entries, child-task enable sets, retry limits, generic timeout settings, restart-script hooks, and recent run statistics.
- WebUI run controls: manual Maa runs, manual-triggered schedules, and tool runs support page-local retry counts, graceful stop, force-stop controls, and ADB-device conflict arbitration.
## Development

```bash
uv sync
uv run maa-auto-panel --help
```

## MAA runtime

`maa-cli` and MaaCore are installed project-locally under `data/runtime/maa/`.
Framework-owned persistent files live under the configurable `data/` root;
disposable APK/patch downloads live separately under `cache/downloads/`.

Managed maa-cli config lives under `data/config/maa/`; framework settings,
schedules, and scripts live under `data/config/framework/`.

Use the wrapper to run `maa` with the project-local config/data/cache/state:

```bash
scripts/maa-env maa version
scripts/maa-env maa list
```

Task files under `data/config/maa/tasks/` may contain framework metadata such as
`[tasks.framework]`, which raw `maa-cli` rejects. Use the framework runner or
WebUI to run those tasks; it generates a sanitized temporary maa-cli config under
`data/runtime/maa/generated-configs/`.

The framework wrapper treats `maa-cli` as an unreliable external process;
use the WebUI for managed runs with logging and diagnostics.

## Process lifecycle

The WebUI handles SIGTERM through FastAPI lifespan shutdown. It closes SSE
connections, stops scheduler triggers, rejects new runs, gives all active runs
a shared 60-second graceful window, then force-kills remaining process groups
and waits another 15 seconds for persistence and thread cleanup. Container and
service managers should allow a 120-second stop grace period.

## WebUI

The WebUI is split into a Python FastAPI backend and an independent React +
TypeScript + Vite frontend under `frontend/`. The backend serves
`frontend/dist` when the frontend has been built.

Install and build the frontend:

```bash
cd frontend
npm install
npm run build
```

Start the backend, which serves `frontend/dist` when it exists:

```bash
uv run maa-auto-panel webui --host 0.0.0.0 --port 8000
```

Override the two storage roots with `--data-dir`/`MAA_AUTO_PANEL_DATA_DIR`
and `--cache-dir`/`MAA_AUTO_PANEL_CACHE_DIR`. They are intentionally separate:
deleting the download cache must not remove framework state.

From the LAN, open:

```text
http://192.168.5.15:8000/
```

The current slice reads local managed maa-cli config files from:

- `data/config/maa/profiles/`
- `data/config/maa/tasks/`
- `data/config/framework/schedules/`

It can select a task config, list and edit task items, open a
schema-driven visual editor for supported MaaCore task params, save task
config changes back through the backend, move deleted task config files to a
local recycle folder, edit default Profile/framework/maa-cli settings, trigger
manual resource or maa-cli updates, start `maa run <task> --batch --profile
default`, define scheduled execution configs under `/schedule`, show
retry-scoped structured logs/status in the right pane, and stop or force-stop
active manual, scheduled, or tool processes.
Framework state, durable run-history JSON, and diagnostics are separated.
Recent runs and scheduler bookkeeping live as readable JSON under
`data/state/framework/`; visible per-run, per-retry history is under
`data/history/framework/runs/`.
Both are local runtime state and ignored by git. Deletable diagnostic
logs live under `data/debug/framework/`: `framework.log` is the standard Python
logging output for framework/API internals, human-level run events are JSONL
under `events/`, and per-run external-process stdout/stderr grouped by source
(`maa-cli`, tools, scripts) plus MaaCore `asst.log` excerpts are under
`external/`.

Current WebUI routes:

- `/`
- `/tasks/:taskConfig`
- `/tasks/:taskConfig/items/:taskItemId`
- `/schedule`
- `/schedule/:scheduleId`
- `/tools`
- `/settings`

See [docs/maa-runtime.md](docs/maa-runtime.md) for the current layout and config notes.

Default target device:

- ADB serial: `192.168.5.151:5555`
- Package: `com.hypergryph.arknights.bilibili`
