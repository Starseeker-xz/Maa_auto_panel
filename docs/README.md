# Maa Auto Panel Documentation

This directory keeps both mirrored upstream references and project-owned notes/design docs.

## Upstream References

- `maa-upstream/zh-cn/`: mirrored Chinese documentation from `MaaAssistantArknights/MaaAssistantArknights`, branch `archive/dev-v1`, path `docs/zh-cn`.
- `maa-cli/`: selected `maa-cli` schemas and example configs copied from `MaaAssistantArknights/maa-cli`.

## Project Notes

- `maa-reading-notes.md`: first-pass reading notes for the MAA/maa-cli integration model, focused on this project's planned retry/fallback/scheduling wrapper.
- `architecture-direction.md`: handoff-oriented direction notes for the planned Web UI orchestration framework.
- `maa-runtime.md`: current project-local `maa-cli`/MaaCore runtime, managed config layout, run/retry history and SSE behavior, and operational notes.

## Current Project Shape

- Python backend/control plane: `src/maa_auto_panel/`.
- Managed MAA/framework config: `data/config/maa/`.
- Ignored local runtime, generated config, logs, and cache: `data/runtime/maa/`.
- React/Vite frontend: `frontend/`.
- FastAPI serves `frontend/dist` and exposes config/run APIs under `/api/`.

## High-Value Upstream Files

- `maa-upstream/zh-cn/manual/cli/install.md`: maa-cli install and MaaCore/resource install flow.
- `maa-upstream/zh-cn/manual/cli/usage.md`: maa-cli commands, predefined tasks, custom task execution, logs.
- `maa-upstream/zh-cn/manual/cli/config.md`: config directory, custom tasks, profile fields, hot update options.
- `maa-upstream/zh-cn/protocol/integration.md`: MaaCore task types and task parameters.
- `maa-upstream/zh-cn/protocol/callback-schema.md`: MaaCore callback events and structured failure/progress data.
- `maa-upstream/zh-cn/protocol/task-schema.md`: internal task pipeline fields, retry limits, `next`, `onErrorNext`, `exceededNext`.
- `maa-upstream/zh-cn/manual/connection.md`: ADB address/config/touch mode notes.
- `maa-upstream/zh-cn/manual/device/linux.md`: Linux/container support, including redroid.
- `maa-cli/schemas/*.json`: JSON schemas for generated maa-cli config validation.
- `maa-cli/config_examples/`: reference TOML/YAML/JSON examples, including `tasks/full-current.toml` as the broad current task-param reference.
