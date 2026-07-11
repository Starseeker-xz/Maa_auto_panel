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

- [`maa-upstream/zh-cn/manual/cli/install.md`](https://docs.maa.plus/zh-cn/manual/cli/install.html): maa-cli installation, custom `MAA_INSTALL_DIR`, self-update, and `maa install` for MaaCore/resources.
- [`maa-upstream/zh-cn/manual/cli/usage.md`](https://docs.maa.plus/zh-cn/manual/cli/usage.html): MaaCore install/update commands, predefined/custom task execution, logs, directory and version inspection commands.
- [`maa-upstream/zh-cn/manual/cli/config.md`](https://docs.maa.plus/zh-cn/manual/cli/config.html): `MAA_CONFIG_DIR`, custom tasks, profiles, conditions, batch behavior, and hot-update options.
- [`maa-upstream/zh-cn/protocol/integration.md`](https://docs.maa.plus/zh-cn/protocol/integration.html): authoritative MaaCore task types/parameters and integration interfaces; use with the current copied schemas because maa-cli does not validate every task parameter itself.
- `maa-upstream/zh-cn/protocol/callback-schema.md`: MaaCore callback events and structured failure/progress data.
- `maa-upstream/zh-cn/protocol/task-schema.md`: internal task pipeline fields, retry limits, `next`, `onErrorNext`, `exceededNext`.
- `maa-upstream/zh-cn/manual/connection.md`: ADB address/config/touch mode notes.
- `maa-upstream/zh-cn/manual/device/linux.md`: Linux/container support, including redroid.
- `maa-cli/schemas/*.json`: JSON schemas for generated maa-cli config validation.
- `maa-cli/config_examples/`: reference TOML/YAML/JSON examples, including `tasks/full-current.toml` as the broad current task-param reference.
