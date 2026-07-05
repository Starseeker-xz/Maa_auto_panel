# Linux MAA

Linux-side automation helpers for running MaaAssistantArknights against Android containers.

Current packaged features:

- `linux-maa webui`: start the local FastAPI + React WebUI.
- WebUI tools: game update (download and install Bilibili Arknights APK) is available as an integrated third-party tool via `python -m linux_maa.tools.game update-game`.
- WebUI scheduled execution: define per-schedule task/profile bindings, game-day-aware time entries, child-task enable sets, retry limits, generic timeout settings, restart-script hooks, and recent run statistics.
- WebUI run controls: manual Maa runs, manual-triggered schedules, and tool runs support page-local retry counts, graceful stop, and force-stop controls.
## Development

```bash
uv sync
uv run linux-maa --help
```

## MAA runtime

`maa-cli` and MaaCore are installed project-locally under `runtime/maa/`.
That directory is ignored by git because it contains downloaded binaries,
MaaCore libraries/resources, logs, cache, generated config, and local state.

Managed maa-cli config is kept separately under `config/maa/`. Local config
under `config/maa/` and `config/linux-maa/` is ignored by git so manual test
edits do not pollute source commits.

Use the wrapper to run `maa` with the project-local config/data/cache/state:

```bash
scripts/maa-env maa version
scripts/maa-env maa list
```

Task files under `config/maa/tasks/` may contain Linux MAA metadata such as
`[tasks.linux_maa]`, which raw `maa-cli` rejects. Use the framework runner or
WebUI to run those tasks; it generates a sanitized temporary maa-cli config under
`runtime/maa/generated-configs/`.

The framework wrapper treats `maa-cli` as an unreliable external process;
use the WebUI for managed runs with logging and diagnostics.

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
uv run linux-maa webui --host 0.0.0.0 --port 8000
```

From the LAN, open:

```text
http://192.168.5.15:8000/
```

The current slice reads local managed maa-cli config files from:

- `config/maa/profiles/`
- `config/maa/tasks/`
- `config/linux-maa/schedules/`

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
`state/linux-maa/`; visible per-run, per-retry history is under
`history/linux-maa/runs/`.
Both are local runtime state and ignored by git. Deletable diagnostic
logs live under `debug/linux-maa/`: `framework.log` is the standard Python
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
