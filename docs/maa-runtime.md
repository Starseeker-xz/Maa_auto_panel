# Project-local MAA runtime

This project keeps downloaded `maa-cli`/MaaCore runtime assets under
`runtime/maa/`. The directory is ignored by git because it contains downloaded
binaries, MaaCore libraries/resources, caches, logs, generated config, and
machine-local state.

Editable maa-cli/framework configuration lives separately under `config/maa/`.

## Layout

- `runtime/maa/bin/maa`: project-local `maa-cli` binary.
- `config/maa`: managed editable configuration (`profiles/`, `tasks/`, `infrast/`, etc.).
- `runtime/maa/generated-configs`: temporary sanitized config generated for `maa-cli`.
- `runtime/maa/data/maa/lib`: MaaCore shared libraries.
- `runtime/maa/data/maa/resource`: bundled MaaCore resources.
- `runtime/maa/data/maa/MaaResource`: hot-update resource repository.
- `runtime/maa/cache/maa`: downloaded archives and metadata cache.
- `runtime/maa/state/maa/debug`: default log directory.

Use `scripts/maa-env` to run `maa` with these paths:

```bash
scripts/maa-env maa version
scripts/maa-env maa list
scripts/maa-env maa run test --batch
```

## Current profile

`config/maa/profiles/default.toml` was initialized from the uploaded
Windows GUI config:

- ADB address: `192.168.5.151:5555`
- client: `Bilibili`
- connection config: `CompatPOSIXShell`
- touch mode: `ADB`
- `kill_adb_on_exit = false`

The Windows GUI config used `General`, Windows ADB paths, and `maatouch`. The
Linux runtime uses the system `adb` from `PATH`, Linux-compatible connection
settings, and ADB touch input. The first real test run showed a MaaTouch-side
`NullPointerException`, so `MaaTouch` is not the default here.

## Current managed task configs

`config/maa/tasks/test.toml` is a first-pass conversion of the uploaded
`test` GUI task queue. It currently includes explicit Linux MAA metadata ids
under each task's `[tasks.linux_maa]` namespace, which the framework strips
before invoking raw `maa-cli`:

- `StartUp` for Bilibili.
- `Award`.
- `Mall`.
- `Infrast`, using `config/maa/infrast/排班.json` and `plan_index = 3`.
- `Fight` with `1-7`, no medicine/stones.
- `Recruit`.

Two smaller diagnostic task files are also present:

- `startup-smoke`: only runs StartUp.
- `award-no-mail`: runs StartUp plus Award with `mail = false`, for isolating
  the mail submission/offline failure seen in the first `test` run.

Raw `maa-cli run <task>` rejects unknown framework metadata. Use the framework
runner or WebUI when task files contain `[tasks.linux_maa]` fields. The runner
generates sanitized temporary JSON task files under:

```text
runtime/maa/generated-configs/<run-id>/tasks/
```

It symlinks non-task config directories, such as `profiles/` and `infrast/`,
into that generated config root.

## WebUI runner behavior

The FastAPI WebUI runs one active `maa-cli` process at a time. Run state is
currently in memory only; it is lost when the backend restarts.

For visible progress, the WebUI invokes `maa-cli` with an explicit log file and
verbosity level:

```text
maa run <generated-task> --batch --profile <profile> --log-file=<path> -v
```

The frontend currently submits profile `default`, one attempt, a 900 second
timeout, and info-level logs. Low-level MaaCore debug logs remain under
`runtime/maa/state/maa/debug/` for diagnosis and are not streamed as normal UI
output.

## Config reading and editing

The backend validates task configs in two layers:

- It strips each task item's `linux_maa` namespace with the same metadata
  removal used by the runner, then validates the sanitized result against
  `docs/maa-cli/schemas/task.schema.json`.
- It validates framework metadata separately. The current metadata fields are
  `id`, `unlimited_runs`, `min_daily_successes`, and `important`.

The scheduling metadata is not enforced by the runner yet. `unlimited_runs`
means future scheduled runs should ignore `min_daily_successes` and always run
that item. When `unlimited_runs = false`, `min_daily_successes` is a
non-negative same-day success threshold; `0` means the requirement is already
satisfied and scheduled runs may skip immediately. `important` is a future
policy hint for failure handling.

The task-config API returns parsed task items, per-item `params`, validation
state, and the metadata schema. The frontend uses JSON Forms for the known
MaaCore parameter schemas currently covered by the UI (`StartUp`, `CloseDown`,
`Award`, `Mall`, `Infrast`, `Fight`, and `Recruit`). UI editor templates live in
`frontend/src/config/task-editor-schemas/*.json`; each property may include a
`description`, which is shown from the field label help icon. New task-item
defaults for local UI creation live in
`frontend/src/config/task-item-defaults.json`. Unknown task types are not edited
visually until a template is added.

`docs/maa-cli/config_examples/tasks/full-current.toml` is a broad reference
task config covering the current maa-cli task enum and MaaCore params documented
in `integration.md`. It is a reference template, not a recommended daily run.

Frontend config edits are local-only for now, including added configs, added
task items, renames, deletes, ordering, enable toggles, metadata, and parameter
form edits. Starting a run still uses the saved config file on disk.

## Fight stage list direction

MaaCore `Fight` accepts one `stage` string. MAA GUI's candidate-stage list is a
GUI-layer feature: it loads `gui/StageActivityV2.json` plus
`resource/tasks/tasks.json`, merges permanent and activity stages with open/close
time data, and stores a `StagePlan` list. Before starting the task, it chooses
the first currently open stage from that list; if none are open, the task is
skipped.

To keep this WebUI's task editors clean, the same behavior should be modeled
outside the generic `Fight` params form: a small stage-plan helper should manage
candidate stages and resolve them to a single MaaCore `stage` value before
config serialization or scheduled execution. The plain JSON Forms `Fight` editor
should continue to expose MaaCore's actual `stage` parameter.

## Docker direction

For Docker, keep this same split:

- image: install `adb`, `maa-cli`, Python app code, and any framework service.
- volume: mount editable config under `/app/config/maa` and runtime state/cache
  under `/app/runtime/maa` or dedicated data volumes.
- entrypoint: run commands through the same environment variables used by
  `scripts/maa-env`.

## Documentation-first rule

MAA documentation in this repository is detailed and should be the first source
for implementation decisions. Do not start with exploratory trial-and-error for
maa-cli/MaaCore behavior when the local docs cover the area.

Use these references first:

- `docs/maa-upstream/zh-cn/manual/cli/`: maa-cli usage, config layout, task
  files, conditions, profile/static/instance options, and import behavior.
- `docs/maa-upstream/zh-cn/protocol/integration.md`: MaaCore task parameters
  and integration API.
- `docs/maa-upstream/zh-cn/protocol/base-scheduling-schema.md`: custom Infrast
  schedule JSON.
- `docs/maa-upstream/zh-cn/protocol/callback-schema.md`: callback/progress
  events and user-facing status extraction.

If these docs are insufficient or appear stale, inspect the actual MAA/maa-cli
source code before inventing behavior or relying on experiments.
