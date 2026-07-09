# Session 2026-07-06_0037-callback-run-manager

## Goal

- 回收上一轮 run manager 重构中过度实现的 driver-owned-loop 设计。
- 用户修正后的目标：manager 接收初始命令和可选 callbacks，由 manager 内置运行、重试、日志、状态、持久化、停止、脚本 hook 循环；外部 callback 只做决策和必要副作用。
- 明确要求：
  - 取消 `RunDriver` 设计。
  - `CommandRunDriver` 降级为 manager 内置默认模式。
  - `RunContext` 不应继续作为胖 manager 控制台存在。
  - 外部脚本是 manager 默认支持能力，可在 before_run / after_run / before_retry / after_retry 四个时点触发，输出进日志管线并使用专属 source 标签和创建方传入模板。

## Startup

- Read `~/.codex/lessons.md`.
- Read `~/.codex/memories/index.md`; no detailed global memory loaded because this task is project-specific.
- Read `.codex/project-history.md`, `.codex/project-lessons.md`, `.codex/conversations/index.md`.
- Created session folder `.codex/conversations/2026-07-06_0037-callback-run-manager/`.

## Implementation Preparation

- Before code edits, inspect current `run_manager/manager.py`, `command.py`, `logs.py`, and migrated domain managers.
- Intended direction:
  - Add callback-first built-in loop to `GenericRunManager`.
  - Remove or stop using driver-owned lifecycle.
  - Keep useful infrastructure: state/store/coordinator/resources/router/log profile/process wrapper.
  - Migrate tool and maintenance first because they should become default command runs with almost no callbacks.
  - Migrate manual and scheduler by moving decisions into callback objects/functions while manager keeps the loop.
  - Move script execution into manager built-in hook support.

## Verification Plan

- After each substantial step:
  - `uvx ruff check src tests`
  - `uv run python -m compileall -q src tests`
  - targeted tests for touched domain
  - `uv run pytest -q`
  - `git diff --check`

## Progress

- Confirmed `RunAttempt.max_retries` landed before context compaction.
- Replaced `RunDriver`/`CommandRunDriver` execution with manager-owned command loop in `GenericRunManager`.
- Added stop guards around retry preparation so a stop request prevents `before_retry`, retry-start text, and generic retry-next text from being emitted after interruption.
- Migrated manual MAA execution from a private driver loop to `ManualMaaRunCallbacks`.
- Migrated scheduled MAA execution from a private driver loop to `ScheduledMaaRunCallbacks`; restart scripts now use manager `RunScriptHooks`.
- Rewrote tests away from `RunContext`/`RunDriver`/`CommandRunDriver`.
- Rewrote `RUN_MANAGER_REFACTOR_PLAN.md` so it documents the current callback-first architecture rather than the superseded driver design.

## Verification Results

- `rg -n "RunContext|RunDriver|CommandRunDriver|CommandRunTextTemplates|driver=|log_buffer_factory|ScheduledMaaRunDriver|ManualMaaRunDriver" src tests` returned no matches.
- `uvx ruff check src tests` passed.
- `uv run python -m compileall -q src tests` passed.
- `uv run pytest -q` passed: 65 tests.
- `git diff --check` passed.

## Final Notes

- The user-reported stop artifact is covered by `tests/test_run_manager.py::test_generic_run_manager_stop_current_adds_event_and_does_not_prepare_next_retry`.
- Persistent handoff updated in `.codex/project-history.md`, `.codex/project-lessons.md`, and `.codex/conversations/index.md`.
