# Architecture Direction

Source session: `2026-06-26_1620-maa-cli-framework-docs`

This document records current direction-level decisions for handoff. It is not a final implementation spec.

## Product Direction

The project should become a high-availability Web UI framework around `maa-cli`, not just a thin command wrapper.

Primary goals:

- Provide a Web UI that can author configuration and run tasks similarly to MAA GUI.
- Schedule and execute `maa-cli` workflows.
- Detect failures from `maa-cli` logs/output rather than integrating MaaCore directly.
- Retry and fallback at a finer granularity than MAA GUI supports.
- Keep non-core utilities under the same orchestration model: game APK update, MaaCore/resource update, ADB/redroid checks, Android container lifecycle commands, and scheduled external scripts.

Future but important UI goal:

- Provide a unified, user-friendly visual editor for JSON/TOML-style config files, including framework config, maa-cli task config, MAA base/infrastructure config, and other project configs.

## Recommended Mental Model

Treat the framework as a task orchestration platform. `maa-cli` is one runner/action type, not the whole architecture.

Current implementation note (`2026-07-04_1305-unify-run-log-sse`): manual
runs, scheduled runs, tools, and maintenance actions now share a `LiveRun` plus
`LiveRetry` state shape. Live SSE payloads and durable history both use
`{run, retries}`; visible log buffers are retry-scoped. Manual Maa runs,
scheduled Maa runs, and tool runs can use configurable retry counts; scheduled
automatic runs can additionally buffer after every configured number of retry
segments. Maintenance actions remain single-retry runs. Maa task results are
collected from raw `maa-cli` stderr by the Maa run callers instead of being
projected from visible log entries.

Core model:

```text
Workflow
  Step[]
    type: maa_cli | script | game_update | maacore_update | adb_check | notify
    critical: true/false
    retry_policy
    fallback_policy
    timeout
    always_rerun_before_retry
    pre_hooks
    post_hooks
```

Workflow status should be richer than a boolean:

```text
success
soft_failed
retrying
paused
blocked
failed
cancelled
skipped
```

Example target behavior:

- Workflow sequence: `StartUp -> A -> B -> C`.
- If `B` fails and `StartUp` is configured as `always_rerun_before_retry`, retry should run `StartUp -> B -> C`.
- If `StartUp` fails 3 consecutive times, notify through bot integration, pause 5 minutes, then retry.
- If `C` fails but is marked non-critical, the workflow may complete as `soft_failed` or `success_with_warnings` depending on final naming.

## Suggested Project Structure

```text
src/linux_maa/
  app/                    # Web app entrypoint and lifecycle
  api/                    # REST/WebSocket API
  domain/                 # Workflow, step, retry policy, run state models
  scheduler/              # Timers, queueing, locks
  runner/                 # Process execution primitives
  logs/                   # WebUI-visible log buffers, parsers, and process-output classification
  retry/                  # Retry/fallback policy engine
  config/                 # Schemas, loading, validation, migration
  storage/                # Text/file persistence and retention
  notify/                 # Bot/webhook/email notification adapters
  integrations/
    maa_cli.py            # maa-cli adapter
    adb.py                # ADB/redroid helper
    game_update.py        # Current game update feature
    scripts.py            # External script runner
  cli.py                  # Admin/development CLI
frontend/                 # Optional separate frontend app
configs/
  examples/
  schemas/
var/
  config/
  logs/
  runs/
  cache/
docs/
```

## Configuration Direction

Recommended defaults:

- Human-authored project config: TOML.
- Runtime/API representation: JSON-compatible Pydantic models.
- Validation and UI forms: JSON Schema generated from Pydantic or maintained explicitly.
- maa-cli config: generated as the format `maa-cli` expects, but not treated as the framework's source-of-truth model.

State/config separation:

- `var/config`: user config.
- `var/runs`: workflow run records.
- `var/logs`: detailed framework/process logs plus parsed high-level event logs.
- `var/cache`: APKs, MaaCore/resource caches, downloaded assets.

## Backend Technology Direction

Current backend stack:

- FastAPI for HTTP/WebSocket API.
- Pydantic v2 for config/domain models and JSON Schema generation.
- A synchronous `subprocess.Popen`-based run manager in a background thread for the first WebUI slice.

Still recommended:

- Text-first run history and logs for this project's current scale; avoid adding
  SQL unless query complexity clearly requires it.
- Keep framework state and diagnostic logs as separate concerns. State files
  should use readable JSON documents under a state root; diagnostic logs should
  use framework logging/event/external-process log modules under a debug/log
  root.
- APScheduler for future scheduling only if the current lightweight loop becomes
  too limited.
- Async subprocess execution once concurrent process control, log streaming, or cancellation grows beyond the current single-run model.
- `tomlkit` if preserving comments/formatting in TOML becomes important.

Important rule: treat `maa-cli` as an external process with uncertain behavior. Every invocation must capture:

- command arguments,
- environment,
- timeout,
- exit code,
- stdout/stderr,
- log file paths,
- parsed failure classification,
- start/end timestamps.

## Frontend Direction

Current frontend stack:

- React + TypeScript + Vite under `frontend/`.
- React Router routes: `/`, `/tasks/:taskConfig`, `/tasks/:taskConfig/items/:taskItemId`, `/schedule`, `/schedule/:scheduleId`, `/tools`, and `/settings`.
- Local shadcn-style components with Radix primitives, lucide icons, Tailwind CSS v4, `@tailwindcss/vite`, and `tw-animate-css`.

Current UI shape:

- Persistent sidebar for `主界面`, expandable `定时执行`, `小工具`, and `设置`.
- Main page uses a three-column operational layout: task config/task-item list, schema-driven task editor, and info-level log/status panel.
- Schedule page now has an overview route and per-schedule detail route. The detail route uses a three-column operational layout: bound task/time-entry controls, per-schedule settings/statistics, and structured scheduled-run logs.
- Profile selection is hidden from the main page for now and defaults to `default`.
- Settings page edits framework timezone/theme/default Profile/maa-cli update settings. Schedule configs keep their own Profile copy.

Current config editing behavior:

- Frontend edits are staged as drafts and only affect disk after explicit save.
- Backend validates structured task config saves before writing `config/maa/tasks/*`.
- Deleting a config moves the file to `config/maa/.trash/` through a reusable trash manager.

Recommendation remains: keep expanding workflow execution, run history, log viewing, and retry/fallback behavior before over-investing in new config-editor surfaces.

## Testing Direction

The retry/fallback engine must be testable without a real Android device or real `maa-cli`.

Create fake runners that emit predefined outcomes such as:

- `StartUp` fails 3 times, then succeeds.
- `B` fails once, then succeeds after rerunning `StartUp`.
- `C` fails but is non-critical.
- `maa-cli` exits 0 but logs contain a known failure marker.

This is the safest way to make the high-availability behavior reliable.
