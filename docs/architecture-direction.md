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
  logparse/               # maa-cli log parsing and failure classification
  retry/                  # Retry/fallback policy engine
  config/                 # Schemas, loading, validation, migration
  storage/                # SQLite/filesystem persistence
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
- `var/logs`: raw logs and parsed event logs.
- `var/cache`: APKs, MaaCore/resource caches, downloaded assets.

## Backend Technology Direction

Recommended first backend stack:

- FastAPI for HTTP/WebSocket API.
- Pydantic v2 for config/domain models and JSON Schema generation.
- SQLite plus SQLModel or SQLAlchemy for persistent run history.
- APScheduler for the first scheduling implementation.
- Async subprocess execution for `maa-cli` and external scripts.
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

Two plausible UI paths:

- Simple first UI: FastAPI templates plus HTMX/Alpine.js.
- Strong interactive config UI: React or Vue plus a JSON Schema form renderer.

Recommendation: do not build the full config editor first. Build workflow execution, run history, log viewing, and retry/fallback engine first. Add schema-driven config editing after the model stabilizes.

## Testing Direction

The retry/fallback engine must be testable without a real Android device or real `maa-cli`.

Create fake runners that emit predefined outcomes such as:

- `StartUp` fails 3 times, then succeeds.
- `B` fails once, then succeeds after rerunning `StartUp`.
- `C` fails but is non-critical.
- `maa-cli` exits 0 but logs contain a known failure marker.

This is the safest way to make the high-availability behavior reliable.

