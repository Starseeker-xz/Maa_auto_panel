# Project Lessons

- `2026-06-26_1727-webui-config-runner`: With the currently resolved FastAPI/Starlette versions, `fastapi.testclient.TestClient` fails unless the extra `httpx2` package is installed. For now, verify the WebUI with a real `uvicorn` server plus `curl`, or intentionally add the test dependency before writing TestClient-based tests.

- `2026-06-29_1929-shadcn-sidebar`: In local shadcn/Radix wrappers, do not use `Slot`/`asChild` in a component that injects multiple sibling children around the slotted child. Radix `Slot` expects a single valid child and can cause a browser runtime blank page. For sidebar navigation, use a real single-child `Link` component or a button with React Router `useNavigate()`.

- `2026-06-29_2137-project-state-docs`: When changing code, config layout, runtime behavior, dependencies, CLI commands, WebUI routes, or frontend structure, explicitly check whether `README.md`, `docs/README.md`, `docs/maa-runtime.md`, `docs/architecture-direction.md`, `.codex/project-history.md`, `.codex/project-lessons.md`, and the current session file need updates. This project relies on those files as active handoff state, not passive notes.

- `2026-06-29_2137-project-state-docs`: The project is still early-stage. For redesigns or upgrades, prefer simplifying the architecture and deleting obsolete functionality over preserving old behavior as fallback. Keep fallback paths only when there is a concrete current operational reason.

- `2026-06-30_0014-task-editor-fixes`: When splitting frontend JSON editor templates, update the template aggregation/import code and verify all schema enum forms are still routed to custom renderers. `oneOf`/`const` titled options require `isOneOfEnumControl`; otherwise the intended select renderer may not apply even though TypeScript builds.

- `2026-06-30_0124-config-save-delete`: When testing FastAPI against a scratch repo, use `create_app(explicit_repo_root)` after the 2026-06-30 fix; before that fix, `create_app(repo_root)` still called `find_repo_root(repo_root)` and could climb to the real repository, causing tests to touch real `config/maa`.

- `2026-06-30_0124-config-save-delete`: On the main task editor route, keep the selected task config derived from the URL as the single source of truth. A separate `taskConfig` state plus an `initialTaskConfig` ref caused route changes to be overwritten back to the initial config when effects reran, locking the UI on `/tasks/award-no-mail`.

- `2026-06-30_0124-config-save-delete`: Browser-based frontend checks are now available through the project `frontend` dev dependency `playwright` and Chromium installed under `/root/.cache/ms-playwright/`. For visual/layout verification, use Playwright screenshots plus overflow checks instead of relying only on `npm run build` and `curl`.

- `2026-06-30_1743-fix-infrast-plan-select`: For JSON Forms controls that manage both visible `params` and `linux_maa.managed_params`, avoid firing separate parent updates in the same UI event. The main page's draft update path can otherwise apply stale item snapshots and overwrite the visible param change. Prefer one combined callback/patch for the param value and managed metadata.

- `2026-06-30_1743-fix-infrast-plan-select`: `MaaRuntime` does not have a `discover()` helper. For direct ConfigManager/runtime checks, construct it with `MaaRuntime(find_repo_root())`.

- `2026-06-30_1934-scheduled-retry-architecture`: Repository tests require the uv dev dependency group; before this session `uv run pytest` failed because pytest was not installed. Keep `pytest` in `[dependency-groups].dev` and run tests with `uv run pytest`.

- `2026-06-30_2056-scheduled-execution`: Repository-wide `rg` searches can explode into `frontend/node_modules/` and mirrored upstream docs. For audit searches, pass targets such as `src frontend/src config README.md docs/architecture-direction.md docs/maa-runtime.md` or exclude with `-g '!frontend/node_modules/**' -g '!docs/maa-upstream/**' -g '!runtime/**'`.

- `2026-06-30_2056-scheduled-execution`: This environment does not provide a bare `python` executable on PATH. In this repository, run Python checks and scripts with `uv run python ...` so they use the project interpreter and dependencies.

- `2026-06-30_2342-full-project-audit`: Do not put raw scratch artifacts or upstream source checkouts under tracked `.codex/conversations/**/scratch/`. This repository currently has tracked scratch logs/screenshots and gitlink entries for old upstream checkouts, making handoff state noisy and large. Future sessions should keep scratch untracked, summarize durable findings into project history/session files, and update ignore rules during cleanup.

- `2026-07-01_1312-explain-log-flow`: When splitting one domain's implementation into multiple files, keep those files inside a domain subpackage instead of scattering them as sibling modules in the parent package. Example: log internals belong under `src/linux_maa/maa/logs/`, with `__init__.py` preserving the public import surface.

- `2026-07-01_1312-explain-log-flow`: When browser-testing pages that open SSE/EventSource connections, do not wait for Playwright `networkidle`; the long-lived event stream keeps the page non-idle and causes timeouts. Use `domcontentloaded` plus targeted DOM assertions or fixed short waits.

- `2026-07-01_1506-sse-log-delta`: For this project, code changes must start with a focused audit of the affected module before implementation. If the audit reveals clear architectural risks such as duplicated logic, muddy module boundaries, high-frequency full-state polling, unbounded log growth, or stale fallback paths, proactively propose and handle low-to-medium-risk improvements instead of only applying the narrow requested fix. Keep each change focused on one module/boundary at a time, record durable conclusions in project state, and follow the detailed policy in `PROJECT_EXECUTION_POLICY.md`.

- `2026-07-01_2153-manage-service-history`: Do not manage the WebUI by manually searching process names or trusting `runtime/linux-maa/webui.pid`; that PID file was stale after a detached launch. Use the temporary systemd unit `linux-maa-webui.service` for lifecycle operations: `systemctl start linux-maa-webui`, `systemctl stop linux-maa-webui`, `systemctl status linux-maa-webui`, and `journalctl -u linux-maa-webui`.

- `2026-07-01_2153-manage-service-history`: Do not dump high-frequency raw process output into high-level JSONL event logs, and do not reuse one "history/log" class for state plus diagnostics. Keep framework runtime state as readable JSON under `state/linux-maa/`; keep disposable diagnostics under `debug/linux-maa/`; use Python `logging` for framework debug/API traces; keep maa-cli stdout/stderr physically separated under `debug/linux-maa/external/maa-cli/`; reserve event JSONL for human-meaningful run events.
