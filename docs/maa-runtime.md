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
- touch mode: `MaaTouch`
- `kill_adb_on_exit = false`

The Windows GUI config used `General`, Windows ADB paths, and `maatouch`. The
Linux runtime uses the system `adb` from `PATH` and Linux-compatible connection
settings. Earlier real-device testing showed a MaaTouch-side
`NullPointerException`; if this recurs, switch the profile or schedule profile
copy back to ADB touch mode before retesting automation stability.

## Current managed task configs

`config/maa/tasks/test.toml` is a first-pass conversion of the uploaded
`test` GUI task queue. It currently includes explicit Linux MAA metadata ids
under each task's `[tasks.linux_maa]` namespace. The framework strips or projects
that namespace before invoking raw `maa-cli`:

- `StartUp` for Bilibili.
- `Award`.
- `Mall`.
- `Infrast`, using `config/maa/infrast/排班.json` and `plan_index = 3`.
- `Fight` with `1-7`, no medicine/stones. In the visual editor this is shown as
  a managed stage plan list; the runner resolves it to one currently open
  MaaCore `stage` string before calling `maa-cli`.
- `Recruit`.

Additional task files are also present:

- `startup-smoke`: only runs StartUp.
- `full-current`: broad reference task file for the current maa-cli task enum
  and MaaCore params. It is useful for schema/editor coverage, not as a
  recommended daily run.

Raw `maa-cli run <task>` rejects unknown framework metadata and cannot interpret
Linux MAA runtime placeholders. Use the framework runner or WebUI when task
files contain `[tasks.linux_maa]` fields or `__linux_maa_runtime__:*` values.
The runner generates sanitized temporary JSON task files under:

```text
runtime/maa/generated-configs/<run-id>/tasks/
```

It symlinks non-task config directories, such as `profiles/` and `infrast/`,
into that generated config root.

## Managed parameter projection

The visual editor sometimes needs to keep richer UI state than MaaCore accepts.
That state is stored under each task's `linux_maa.managed_params` map. When a
task config is saved, the MaaCore-facing `tasks.params` value is replaced by a
runtime placeholder; when a run starts, the framework resolves that placeholder
back to the exact value `maa-cli` can consume.

Current managed forms:

- `type = "array"` stores ordered `{ value, enabled }` items in metadata. The
  saved param becomes `__linux_maa_runtime__:array:<key>`, and the runner's
  generic array handler restores only enabled item values.
- `handler = "fight_stage"` stores a Fight stage candidate list. The saved param
  becomes `__linux_maa_runtime__:fight_stage`; the runner chooses the first
  currently open stage through the same stage service used by the API.
  The GUI value "当前/上次" is stored as the framework value
  `__linux_maa_stage__:current_last` so it can be ordered and used as a fallback;
  immediately before `maa-cli` runs, that value maps to MaaCore's empty
  `stage = ""` convention.
- `handler = "infrast_plan_index"` stores the user-selected Infrast plan option.
  The saved param becomes `__linux_maa_runtime__:infrast_plan_index`; the runner
  resolves the auto option by reading the custom scheduling JSON `period` values
  and choosing the currently active plan index.

If a runtime placeholder has no known handler, or a handler cannot resolve a
valid value, the framework disables that child task in the generated config and
adds a skip message to the WebUI run output.

## WebUI runner behavior

The FastAPI WebUI runs one active `maa-cli` process at a time. Run state is
currently in memory only; it is lost when the backend restarts.

For visible progress, the WebUI invokes `maa-cli` with an explicit log file and
verbosity level:

```text
maa run <generated-task> --batch --profile <profile> -v
```

The frontend currently submits profile `default` and info-level logs. Main-page
manual runs are single-shot: they do not apply a WebUI-level timeout or retry
loop. Detailed retry policy is expected to come later from the workflow engine.
Low-level MaaCore debug logs remain under `runtime/maa/state/maa/debug/` for
diagnosis and are not streamed as normal UI output.

The WebUI captures two visible process channels:

- `maa-cli` stdout and stderr are merged with `stderr=subprocess.STDOUT` and read
  from the process pipe. maa-cli writes logs to stderr by default, so this is
  the real-time UI log source. It also captures output such as git fetch text
  and the final `Summary`.
- When info logs are enabled, the framework tees the merged process stream into
  its own `runtime/maa/run-logs/...` artifact. It does not pass `--log-file` to
  maa-cli for WebUI/scheduled live runs, because that can move info callback
  logs out of stderr in the observed maa-cli runtime. Runtime environments force
  `MAA_LOG_PREFIX=Always` so stderr logs keep the timestamp/level prefix expected
  by the structured log parser.

The WebUI run manager does not pass raw `maa-cli` log chunks straight through.
The `src/linux_maa/maa/logs/` package parses framework-level semantics from
info-level `maa-cli` output through configurable chunk rules. `rules.py` defines
the explicit summary rule, task-lifecycle rule, and default line rule;
`translator.py` owns the state machine that applies those rules to a stream.
The task-lifecycle rule opens a child-task panel on `TaskName Start` and closes
it on `TaskName Completed`, `TaskName Error`, or `TaskName Stopped`. Unmatched
lines use the default line rule; when a task panel is active, those lines remain
child messages of that task, preserving current UI behavior.

Framework preprocessing events also enter the same structured log stream;
current examples include the resolved Fight stage and Infrast plan before
`maa-cli` starts. The run-state API exposes structured `log_entries` for UI
rendering and `task_results` for per-child status. The frontend renders these
entries as timeline-style cards, leaving room for future colored text segments
and inline images. Already translated events do not show the original raw log
line in the normal log UI. The final maa-cli `Summary` tail is grouped into one
structured summary panel instead of being rendered as one global log card per
line.

The current-run UI state is delivered through Server-Sent Events:

- `GET /api/runs/current/events` streams the manual run state.
- `GET /api/schedules/current/events` streams the active scheduled run state.

Each stream sends the current state immediately, then sends another complete
`RunState` only after the owning run service reports a state change. The backend
does not poll current state on a fixed interval for SSE; `MaaRunManager` and
`SchedulerService` notify waiting streams through condition variables whenever
they append output, update task state, start a run, stop a run, or finish a run.
Idle streams block until a real update or a 15-second keep-alive timeout. The
legacy JSON endpoints `GET /api/runs/current` and `GET /api/schedules/current`
remain available for one-shot reads and non-SSE clients.

## Config reading and editing

The backend validates task configs in two layers:

- It strips each task item's `linux_maa` namespace with the same metadata
  removal used by the runner, then validates the sanitized result against
  `docs/maa-cli/schemas/task.schema.json`.
- It validates framework metadata separately. The current metadata fields are
  `id`, `unlimited_runs`, `min_daily_successes`, `important`,
  `retry_even_success`, and `managed_params`.

The manual runner does not enforce scheduling metadata. The scheduled execution
service does. `unlimited_runs` means a scheduled time entry should keep running
that item regardless of same-day success counts. When `unlimited_runs = false`,
`min_daily_successes` is a non-negative same-day success threshold for important
tasks; `0` means the requirement is already satisfied and scheduled runs may
skip immediately. `important = false` means the task can run but will not enter
retry; for those tasks, `min_daily_successes` is interpreted as a same-day run
count threshold. `retry_even_success` does not create a retry by itself; it
causes the task to be included when another important task requires retry.

The task-config API returns parsed task items, per-item `params`, validation
state, and the metadata schema. It can also save structured task-item edits back
to `config/maa/tasks/` through `PUT /api/configs/tasks/{name}`. Saves rebuild the
task file from structured data, validate it before writing, and currently support
TOML and JSON output; TOML comments and hand formatting are not preserved by a
visual save.

`DELETE /api/configs/{kind}/{name}` moves the selected config file into the
local recycle folder under `config/maa/.trash/`, including a small
`trash-record.json` with the original path and deletion time. That recycle folder
is ignored by git.

`GET /api/settings` returns the framework settings, default Profile, maa-cli
config, validation state, and the current maintenance action. `PUT
/api/settings` writes the framework settings to `config/linux-maa/settings.toml`,
the default Profile to `config/maa/profiles/default.toml`, and the maa-cli config
to `config/maa/cli.toml` after validating the Maa config payloads. Framework
timezone settings support automatic backend-local timezone resolution, fixed UTC
offsets, and IANA names such as `Europe/London` so daylight-saving offsets are
resolved at save time. The frontend can also store the browser-reported IANA
timezone when the user's client timezone differs from the backend/container
timezone.

`GET /api/maintenance/update-info` compares local `maa version`, local resource
metadata, MaaCore/maa-cli version APIs, and the MaaResource git remote before the
user starts an update. Maintenance update actions are intentionally split:
`core-update` runs `maa update --batch` for MaaCore and the bundled/base
resources, `resource-update` runs `maa hot-update --batch` for hot-updateable
MaaResource content, and `cli-update` runs `maa self update --batch` for the
maa-cli binary.

The frontend uses JSON Forms for the known MaaCore parameter schemas currently
covered by the UI (`StartUp`, `CloseDown`, `Award`, `Mall`, `Infrast`, `Fight`,
and `Recruit`). UI editor templates live in
`frontend/src/config/task-editor-schemas/*.json`; each property may include a
`description`, which is shown from the field label help icon. New task-item
defaults for UI creation live in `frontend/src/config/task-item-defaults.json`.
Unknown task types are not edited visually until a template is added.

The JSON Forms renderer treats arrays with `x-linuxMaaManaged` as managed arrays
and shows per-item enable checkboxes. Plain arrays remain normal arrays without
checkboxes. Dynamic option fields use backend-provided option APIs instead of
hardcoded schema enums. Infrast `filename` and `plan_index` are shown in the
general settings tab as dropdowns; `plan_index` is disabled when no custom
schedule file is selected. Fight stage plans are edited as a managed array whose
options come from `GET /api/maa/stages`.

`docs/maa-cli/config_examples/tasks/full-current.toml` is a broad reference
task config covering the current maa-cli task enum and MaaCore params documented
in `integration.md`. It is a reference template, not a recommended daily run.

Frontend config edits are staged as in-memory drafts until the user clicks the
main-page save button. The save/reset controls appear after any staged change.
Starting a run still uses the saved config file on disk, so unsaved drafts do not
affect `maa-cli`.

## Scheduled execution

Scheduled execution configs live under `config/linux-maa/schedules/*.toml`.
Each config binds one maa-cli task config and stores its own Profile copy. The
default Profile in Settings is only the template used for new schedules and for
manual main-page runs.

The scheduler persists run records, attempts, same-day task counters, and
trigger de-duplication in `runtime/linux-maa/scheduler.sqlite3`. The runtime
directory remains ignored by git.

Schedule entries store their own `task_ids`; these are independent from the
main task editor's `enable` checkbox. When a scheduled attempt is generated, the
selected child tasks are filtered into a temporary maa-cli task file and are
force-enabled in that generated file.

Game-day calculations currently use maa-cli's client-timezone convention for
Chinese servers: `Official`, `Bilibili`, and `txwy` use an effective UTC+4
game-day timezone, equivalent to a China-server reset at Beijing 04:00. The
legacy local schema value `Txwy` is still accepted for compatibility. In
`Europe/London` during summer time this means a local 21:00 reset, so a
04/08/16/22 local schedule is displayed and evaluated in the game-day order
22 -> 04 -> 08 -> 16.

Retry selection follows the framework metadata:

- `retry_even_success = true`: rerun when any retry is happening.
- important + `unlimited_runs = true`: run every scheduled entry and retry until
  it succeeds for that run.
- important + `unlimited_runs = false`: run while same-day successes are below
  `min_daily_successes`; retry only when remaining enabled schedule entries are
  no greater than remaining required successes.
- non-important: run according to unlimited/minimum-run settings but never enter
  retry.

Retry attempts preserve the original task-config order. The service also tracks
which child tasks have already succeeded within the current scheduled run, so a
later retry attempt does not requeue an already successful important task just
because it was absent from the immediately previous retry subset.

The WebUI exposes:

- `GET/POST /api/schedules`
- `GET/PUT/DELETE /api/schedules/{schedule_id}`
- `POST /api/schedules/{schedule_id}/run`
- `GET /api/schedules/current`
- `POST /api/schedules/current/stop`

Restart-script hooks are configured by schedule. Scripts are read from
`config/linux-maa/scripts/`; a script can declare string variables with comments
like `# linux-maa-var: CT_ID|容器 ID|151`, and those values are injected as
environment variables when the hook runs.

## Fight stage list API

MaaCore `Fight` accepts one `stage` string. MAA GUI's candidate-stage list is a
GUI-layer feature: it loads `gui/StageActivityV2.json` plus
`resource/tasks/tasks.json`, merges permanent and activity stages with open/close
time data, and stores a `StagePlan` list. Before starting the task, it chooses
the first currently open stage from that list; if none are open, the task is
skipped.

The backend now exposes only the list-building half of that GUI behavior through
`GET /api/maa/stages`. By default it returns currently open, non-hidden stage
candidates; `include_unavailable=true` also returns stages that are known but not
currently open. The API accepts `client`, maps `Bilibili` to `Official` like the
GUI, reads the local `runtime/maa/cache/maa/StageActivityV2.json`, and includes
the MaaCore version and source paths in the response.

The same stage service is also used by the runner for managed Fight stage plans:
`linux_maa.managed_params.stage` keeps the user-facing candidate list, while the
generated task config contains the first currently open stage as the single
MaaCore `Fight.stage` value. The API returns `value =
"__linux_maa_stage__:current_last"` and `maa_value = ""` for "当前/上次"; UI code
uses the non-empty `value`, while the runner writes `maa_value` semantics.

## Infrast option APIs

`GET /api/maa/infrast/files` lists JSON files under `config/maa/infrast/` for
the Infrast custom schedule dropdown. It also returns an explicit empty option
for "not selected" so the UI can disable plan selection.

`GET /api/maa/infrast/plans?filename=<file>` reads the selected custom schedule
JSON and returns a first auto option plus one option per plan. The auto option
means "choose by time"; the backend resolves it at run time by checking each
plan's `period` against the current local time.

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
