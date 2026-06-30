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
