# Maa Auto Panel

Automation panel for running MaaAssistantArknights against Android containers.

Current packaged features:

- `maa-auto-panel webui`: start the local FastAPI + React WebUI.
- WebUI tools: game update (download and install Bilibili Arknights APK) is available as an integrated third-party tool via `python -m maa_auto_panel.tools.game update-game`.
- WebUI scheduled execution: define per-schedule task/profile bindings, game-day-aware time entries, child-task enable sets, retry limits, generic timeout settings, restart-script hooks, and recent run statistics.
- WebUI run controls: manual Maa runs, manual-triggered schedules, and tool runs support page-local retry counts, graceful stop, force-stop controls, and ADB-device conflict arbitration.
- Global notifications: runtime missing/update availability and completed manual or scheduled MAA runs are delivered through a global SSE stream, with per-tag Toast policy and a reserved external-sender interface.
## Development

```bash
uv sync
uv run maa-auto-panel --help
```

## MAA runtime

`maa-cli` and MaaCore are installed project-locally under `runtime/maa/`.
Framework-owned persistent files live under the configurable `data/` root;
integration runtimes use the independent `runtime/` root, and disposable
APK/patch downloads live separately under `cache/downloads/`.

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
`runtime/maa/generated-configs/`.

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

Override the three writable roots with `--data-dir`/`MAA_AUTO_PANEL_DATA_DIR`,
`--runtime-dir`/`MAA_AUTO_PANEL_RUNTIME_DIR`, and
`--cache-dir`/`MAA_AUTO_PANEL_CACHE_DIR`. Framework data, replaceable integration
runtimes, and disposable downloads intentionally have separate ownership.

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
Scheduler bookkeeping lives under `data/state/framework/`; recent run records
and the only detailed per-run/retry records live under `data/run-history/`.
Both are local runtime state and ignored by git. `data/debug/framework/` contains
only the standard framework/API log and high-level JSONL run events. Child
process diagnostics are grouped by provider under `data/debug/maa/`,
`data/debug/scheduler/`, and `data/debug/tools/`.

Current WebUI routes:

- `/`
- `/tasks/:taskConfig`
- `/tasks/:taskConfig/items/:taskItemId`
- `/schedule`
- `/schedule/:scheduleId`
- `/tools`
- `/settings`

See [docs/maa-runtime.md](docs/maa-runtime.md) for the current layout and config notes.

## Container build contract

Container files currently define the future deployment boundary; the normal
development loop continues to use the existing systemd service. Do not run the
systemd/dev instance and the container instance at the same time against the
same redroid or data directory. Unless a container test or deployment is being
performed deliberately, there is no need to build or start the image.

Build the application image without copying local data, caches, or MAA runtime:

```bash
docker compose build panel
```

The image contains the backend, built frontend, schemas, ADB client, Git, and
runtime installation tools. It intentionally does not contain maa-cli,
MaaCore, resources, user config, history, or ADB credentials.

For a future container deployment, create the host directories and grant them
to container UID/GID `10001`, then set `MAA_PANEL_DATA_PATH`,
`MAA_PANEL_RUNTIME_PATH`, and `MAA_PANEL_DOWNLOAD_CACHE_PATH` if the default `/srv/maa-auto-panel` paths are
not suitable. The default published address is loopback-only; set
`MAA_PANEL_BIND_ADDRESS` explicitly for trusted-LAN access.

Install an isolated runtime into the mounted runtime root with the official
maa-cli installer followed by `maa install`:

```bash
docker compose run --rm panel install-runtime
```

For a clean runtime reinstall:

```bash
docker compose run --rm panel reinstall-runtime
```

The reinstall command removes only `/app/runtime/maa`. Managed MAA config
under `/app/data/config/maa` is outside that directory and is preserved. Normal
`docker compose up` never installs or updates the runtime automatically. See
`BACKEND_AUDIT.md` for the single-instance rule and deployment boundaries.

Default target device:

- ADB serial: `192.168.5.151:5555`
- Package: `com.hypergryph.arknights.bilibili`
