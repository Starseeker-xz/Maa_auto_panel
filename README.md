# Linux MAA

Linux-side automation helpers for running MaaAssistantArknights against Android containers.

Current packaged feature:

- `linux-maa update-game`: fetch the latest Bilibili Arknights Android package, reuse local APK cache or Bilibili incremental patches when possible, and install the package to a target ADB device.

## Development

```bash
uv sync
uv run linux-maa --help
```

## MAA runtime

`maa-cli` and MaaCore are installed project-locally under `runtime/maa/`.
That directory is ignored by git because it contains downloaded binaries,
MaaCore libraries/resources, logs, cache, generated config, and local state.

Managed maa-cli config is kept separately under `config/maa/`.

Use the wrapper to run `maa` with the project-local config/data/cache/state:

```bash
scripts/maa-env maa version
scripts/maa-env maa list
```

Task files under `config/maa/tasks/` may contain Linux MAA metadata such as
`[tasks.linux_maa]`, which raw `maa-cli` rejects. Use the framework runner or
WebUI to run those tasks; it generates a sanitized temporary maa-cli config under
`runtime/maa/generated-configs/`.

The framework wrapper treats `maa-cli` as an unreliable external process and
retries coarse failures:

```bash
uv run linux-maa run-maa-task test --attempts 3 --timeout 900
```

## WebUI

The WebUI is split into a Python FastAPI backend and an independent React +
TypeScript + Vite frontend under `frontend/`.

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

The first slice reads managed maa-cli config files from:

- `config/maa/profiles/`
- `config/maa/tasks/`

It can select a profile and task, start `maa run <task> --batch --profile <profile>`,
show the info-level maa-cli log/status in the right pane, and stop the active
process. The left pane lists task names from the selected task config; the center
pane is reserved for visual config editing. Low-level MaaCore debug logs such as
`asst.log` stay in the runtime directory for diagnosis and are not streamed in
the WebUI.

See [docs/maa-runtime.md](docs/maa-runtime.md) for the current layout and config notes.

Default target device:

- ADB serial: `192.168.5.151:5555`
- Package: `com.hypergryph.arknights.bilibili`
