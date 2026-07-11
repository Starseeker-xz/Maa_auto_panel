# Project-local MAA runtime

This project keeps downloaded `maa-cli`/MaaCore runtime assets under
`data/runtime/maa/`. The data root is ignored by git because it contains downloaded
binaries, MaaCore libraries/resources, caches, logs, generated config, and
machine-local state.

Editable maa-cli/framework configuration lives under `data/config/maa/`
and `data/config/framework/`. These local config directories are ignored by git
because they are routinely edited for manual testing.

## Layout

- `data/runtime/maa/bin/maa`: project-local `maa-cli` binary.
- `data/config/maa`: managed editable configuration (`profiles/`, `tasks/`, `infrast/`, etc.).
- `data/config/framework`: framework settings, schedules, and scripts.
- `data/runtime/maa/generated-configs`: temporary sanitized config generated for `maa-cli`.
- `data/runtime/maa/data/maa/lib`: MaaCore shared libraries.
- `data/runtime/maa/data/maa/resource`: bundled MaaCore resources.
- `data/runtime/maa/data/maa/MaaResource`: hot-update resource repository.
- `data/runtime/maa/cache/maa`: downloaded archives and metadata cache.
- `data/runtime/maa/state/maa/debug`: default log directory.
- `data/debug/framework`: registered diagnostic log root. It is safe to delete when
  only diagnostics are needed temporarily. It contains `framework.log`,
  high-level run-event JSONL files, and external maa-cli/MaaCore log captures.
- `data/state/framework`: registered framework state root. It stores recent run
  records and scheduler bookkeeping that should not be treated as disposable
  debug output.

Use `scripts/maa-env` to run `maa` with these paths:

```bash
scripts/maa-env maa version
scripts/maa-env maa list
scripts/maa-env maa run test --batch
```

## Current profile

`data/config/maa/profiles/default.toml` was initialized from the uploaded
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

`data/config/maa/tasks/test.toml` is a first-pass conversion of the uploaded
`test` GUI task queue. It currently includes explicit framework metadata ids
under each task's `[tasks.framework]` namespace. The framework strips or projects
that namespace before invoking raw `maa-cli`:

- `StartUp` for Bilibili.
- `Award`.
- `Mall`.
- `Infrast`, using `data/config/maa/infrast/排班.json` and `plan_index = 3`.
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
Maa Auto Panel runtime placeholders. Use the framework runner or WebUI when task
files contain `[tasks.framework]` fields or `__framework_runtime__:*` values.
The runner generates sanitized temporary JSON task files under:

```text
data/runtime/maa/generated-configs/<run-id>/tasks/
```

It symlinks non-task config directories, such as `profiles/` and `infrast/`,
into that generated config root.

## Managed parameter projection

The visual editor sometimes needs to keep richer UI state than MaaCore accepts.
That state is stored under each task's `framework.managed_params` map. When a
task config is saved, the MaaCore-facing `tasks.params` value is replaced by a
runtime placeholder; when a run starts, the framework resolves that placeholder
back to the exact value `maa-cli` can consume.

Current managed forms:

- `type = "array"` stores ordered `{ value, enabled }` items in metadata. The
  saved param becomes `__framework_runtime__:array:<key>`, and the runner's
  generic array handler restores only enabled item values.
- `handler = "fight_stage"` stores a Fight stage candidate list. The saved param
  becomes `__framework_runtime__:fight_stage`; the runner chooses the first
  currently open stage through the same stage service used by the API.
  The GUI value "当前/上次" is stored as the framework value
  `__framework_stage__:current_last` so it can be ordered and used as a fallback;
  immediately before `maa-cli` runs, that value maps to MaaCore's empty
  `stage = ""` convention.
- `handler = "infrast_plan_index"` stores the user-selected Infrast plan option.
  The saved param becomes `__framework_runtime__:infrast_plan_index`; the runner
  resolves the auto option by reading the custom scheduling JSON `period` values
  and choosing the currently active plan index.

If a runtime placeholder has no known handler, or a handler cannot resolve a
valid value, the framework disables that child task in the generated config and
adds a skip message to the WebUI run output.

## WebUI runner behavior

Process-backed actions are modeled as a run plus retry segments. Manual Maa
runs, scheduled Maa runs, and tool runs can all carry a UI-provided retry count;
maintenance actions remain single-retry runs. Scheduled automatic runs use the
schedule's `retry.max_retries`, while manual-triggered scheduled runs can
override that count from the page controls. Scheduled automatic runs can also
buffer after every configured number of retry segments for a configured number
of seconds; total retry count does not need to be a multiple of that interval.
Live current-run state is still kept in memory by the owning service, while
completed run records and retry-scoped visible log history are persisted as
JSON.

Live runs that use an ADB device also claim a process-local run resource keyed
by the submitted connection address. The conflict detector is generic, but the
only active rule today is `adb-device` address equality; it intentionally does
not try to discover physical devices or aliases outside the framework. Automatic
scheduled runs have the highest priority, manual-triggered scheduled runs are
next, and ordinary manual/tool runs share the lowest priority. A lower-priority
new run is rejected when it conflicts with a higher-priority active run; an
equal-priority new run waits for the resource to be released; a higher-priority
new run requests stop on the lower-priority owner and waits for that owner to
finish through its normal stop/force-stop thresholds.

For visible progress, Maa-backed runs invoke `maa-cli` with verbosity enabled:

```text
maa run <generated-task> --batch --profile <profile> -v
```

The frontend currently submits profile `default` and info-level logs for manual
runs. WebUI runs do not pass `--log-file` to `maa-cli`, because that can move
info callback logs out of stderr in the observed maa-cli runtime. Low-level
MaaCore debug logs remain under `data/runtime/maa/state/maa/debug/` for diagnosis and
are not streamed as normal UI output. For Maa-backed manual and scheduled retry
segments, the framework records the `asst.log` offset before the retry and
stores that retry's delta under `data/debug/framework/external/maacore/<retry-id>.log`
when MaaCore writes new content.

Timeout handling is shared by all process-backed runs:

- no-output warning/kill thresholds detect a stuck process when stdout/stderr
  has been quiet for too long;
- runtime warning/kill thresholds apply to total process runtime;
- stop warning/kill thresholds apply after a graceful stop is requested.

Manual, tool, and maintenance thresholds come from `framework.run_timeouts` in
settings. Scheduled run thresholds are stored on each schedule. Manual runs also
expose `POST /api/runs/{run_id}/force-stop`; after a normal stop request the UI
turns the stop button into a force-stop action.

The WebUI captures visible process channels through the shared
`maa_auto_panel.logs` module:

- `maa-cli` stdout and stderr are read from separate pipes. The UI still shows a
  merged live view, but detailed per-run text logs store the original streams in
  separate `data/debug/framework/external/maa-cli/<run-id>.stdout.log` and
  `data/debug/framework/external/maa-cli/<run-id>.stderr.log` files. These paths are
  not split by manual/scheduled origin because they are maa-cli process logs.
- Tool stdout/stderr are written to
  `data/debug/framework/external/tools/<run-id>.*.log`; schedule script hook
  stdout/stderr are written to
  `data/debug/framework/external/scripts/<run-id>.*.log`.
- Maa-backed live runs force `MAA_LOG_PREFIX=Always` so stderr logs keep the
  timestamp/level prefix expected by the structured log parser.
- Framework-level events are written to high-level JSONL event files and to the
  global detailed framework log `data/debug/framework/framework.log`. `framework.log`
  uses Python's standard `logging` module with DEBUG, INFO, WARNING, ERROR, and
  CRITICAL levels and records API operations through middleware. Raw child
  process output is kept only in the external stdout/stderr files.

The WebUI run managers do not pass raw process chunks straight through. The
`src/maa_auto_panel/logs/` package owns the generic WebUI-visible log pipeline:
source registration, terminal control characters, block assembly, bounded
`output`, and unified `log_entries`. Each retry segment owns its own
`RunLogBuffer`; once a retry is sealed, its visible blocks are closed and no
longer mutate. Callers register source defaults (`default_tone` and
`default_translate_line`) plus source-scoped block definitions. The pipeline owns
one active block per source and closes blocks with `matched_end`, `superseded`,
`passive_boundary`, or `flush`. MAA-aware rules and translation hooks live in
`src/maa_auto_panel/maa/log_templates.py`, while arbitrary script and tool output use
the generic plain-line fallback. Raw stdout/stderr persistence remains owned by
`Diagnostics`.

The visible log API uses one block shape for all rows. Plain process blocks,
run summaries, git output groups, and framework events differ by open-ended
`kind`, generic block status, `updated_at`, `closed`, and metadata rather than
by separate record types. Task success/failure is intentionally outside the
visible log pipeline: Maa-backed manual and scheduled runs attach a raw-line
collector to `maa-cli` stderr and write retry-local `task_results` from that
collector. Log templates only shape UI text and no longer own task-result
logic.

Framework preprocessing events also enter the same structured log stream as
ordinary `append(..., source="framework:event", metadata={...})` input; current
examples include the resolved Fight stage and Infrast plan before `maa-cli`
starts. The run-state API exposes `run` plus `retries`; each retry exposes
structured `log_entries` for UI rendering and, for Maa-backed runs, separate
`task_results` for per-child status decisions. The frontend renders log entries
with a generic block renderer and a simple retry marker when `max_retries > 1`.
Already translated events do not show the original raw log line in the normal
log UI. The final maa-cli `Summary` tail is grouped into one structured summary
panel instead of being rendered as one global log card per line.

The current-run UI state is delivered through Server-Sent Events:

- `GET /api/runs/current/events` streams the manual run state.
- `GET /api/schedules/current/events` streams the active scheduled run state.
- `GET /api/tools/current/events` streams the active tool run state.
- `GET /api/maintenance/current/events` streams the active maintenance action.

Each stream sends the current state immediately, then sends patch events after
the owning service reports a state change. Patch state contains run-level keys
under `run`, and list deltas are emitted for `retries`; if the client falls
behind the active retry, it can request `retries_from` and re-fetch the unfinished
retry segment. The backend does not poll current state on a fixed interval for
SSE; run services notify waiting streams through condition variables whenever
they append output, update task state, start a run, stop a run, finish a retry,
or finish a run. Idle streams block until a real update or a 15-second
keep-alive timeout. JSON endpoints such as `GET /api/runs/current`,
`GET /api/schedules/current`, `GET /api/tools/current`, and
`GET /api/maintenance/current` remain available for one-shot reads and non-SSE
clients.

## Config reading and editing

The backend validates task configs in two layers:

- It strips each task item's `framework` namespace with the same metadata
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
to `data/config/maa/tasks/` through `PUT /api/configs/tasks/{name}`. Saves rebuild the
task file from structured data, validate it before writing, and currently support
TOML and JSON output; TOML comments and hand formatting are not preserved by a
visual save.

`DELETE /api/configs/{kind}/{name}` moves the selected config file into the
local recycle folder under `data/config/maa/.trash/`, including a small
`trash-record.json` with the original path and deletion time. That recycle folder
is ignored by git.

`GET /api/settings` returns the framework settings, default Profile, maa-cli
config, validation state, and the current maintenance action. `PUT
/api/settings` writes the framework settings to `data/config/framework/settings.toml`,
the default Profile to `data/config/maa/profiles/default.toml`, and the maa-cli config
to `data/config/maa/cli.toml` after validating the Maa config payloads. Framework
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

The JSON Forms renderer treats arrays with `x-frameworkManaged` as managed arrays
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

Scheduled execution configs live under `data/config/framework/schedules/*.toml`.
Each config binds one maa-cli task config and stores its own Profile copy. The
default Profile in Settings is only the template used for new schedules and for
manual main-page runs.

The scheduler persists state as readable JSON under `data/state/framework/`:

- `data/state/framework/run-history/recent-run-records.json`: recent WebUI,
  scheduled, and maintenance run records. Schedule overview "recent runs" is
  derived from this file.
- `data/state/framework/run-history/run-retries.json`: per-retry records for manual,
  scheduled, tool, and maintenance runs. Each row references retry-scoped
  visible log history through `log_entries_file`.
- `data/state/framework/scheduler/daily-task-stats.json`: per-schedule daily
  child-task run/success counters used by retry/skip policy.
- `data/state/framework/scheduler/triggered-schedule-entries.json`: schedule entries
  already triggered for a game day, used to avoid duplicate execution.

The `config/`, `history/`, `debug/`, and `state/` runtime directories remain
ignored by git, but they have different semantics: `config/` is local editable
input, `history/` is durable visible run history, `debug/` is disposable
diagnostics, and `state/` is framework runtime state.

Schedule entries store their own `task_ids`; these are independent from the
main task editor's `enable` checkbox. When a scheduled retry segment is
generated, the selected child tasks are filtered into a temporary maa-cli task
file and are force-enabled in that generated file.

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

Retry segments preserve the original task-config order. Manual and scheduled
Maa runs share the same retry selection helper: after each retry, child tasks
that already succeeded in the current run are skipped on later retries. The
scheduler keeps its schedule-specific daily state and retry policy in
`SchedulerService`.

Schedule retry config is intentionally small: `retry.max_retries` is the number
of retry segments allowed for automatic scheduled runs. `retry.buffer_every_retries`
and `retry.buffer_seconds` optionally pause before the next retry after every N
completed retry segments.

The WebUI exposes:

- `GET/POST /api/schedules`
- `GET/PUT/DELETE /api/schedules/{schedule_id}`
- `POST /api/schedules/{schedule_id}/run`
- `GET /api/schedules/current`
- `POST /api/schedules/current/stop`
- `POST /api/schedules/current/force-stop`

Restart-script hooks are configured by schedule. Scripts are read from
`data/config/framework/scripts/`; a script can declare string variables with comments
like `# framework-var: CT_ID|容器 ID|151`, and those values are injected as
environment variables when the hook runs. Hooks run with the project
`MaaRuntime.env()` environment, so scripts can call the project-local `maa`
binary and see the same `MAA_CONFIG_DIR`/XDG paths as normal framework actions.
Hook stdout/stderr stream live into the scheduled run's visible log and are also
stored under `data/debug/framework/external/scripts/`.

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
GUI, reads the local `data/runtime/maa/cache/maa/StageActivityV2.json`, and includes
the MaaCore version and source paths in the response.

The same stage service is also used by the runner for managed Fight stage plans:
`framework.managed_params.stage` keeps the user-facing candidate list, while the
generated task config contains the first currently open stage as the single
MaaCore `Fight.stage` value. The API returns `value =
"__framework_stage__:current_last"` and `maa_value = ""` for "当前/上次"; UI code
uses the non-empty `value`, while the runner writes `maa_value` semantics.

## Infrast option APIs

`GET /api/maa/infrast/files` lists JSON files under `data/config/maa/infrast/` for
the Infrast custom schedule dropdown. It also returns an explicit empty option
for "not selected" so the UI can disable plan selection.

`GET /api/maa/infrast/plans?filename=<file>` reads the selected custom schedule
JSON and returns a first auto option plus one option per plan. The auto option
means "choose by time"; the backend resolves it at run time by checking each
plan's `period` against the current local time.

## Docker direction

For Docker, keep this same split:

- image: install `adb`, `maa-cli`, Python app code, and any framework service.
- volume: mount editable config under `/app/data/config/maa` and runtime state/cache
  under `/app/data/runtime/maa` or dedicated data volumes.
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
