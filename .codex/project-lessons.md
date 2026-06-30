# Project Lessons

- `2026-06-26_1727-webui-config-runner`: With the currently resolved FastAPI/Starlette versions, `fastapi.testclient.TestClient` fails unless the extra `httpx2` package is installed. For now, verify the WebUI with a real `uvicorn` server plus `curl`, or intentionally add the test dependency before writing TestClient-based tests.

- `2026-06-29_1929-shadcn-sidebar`: In local shadcn/Radix wrappers, do not use `Slot`/`asChild` in a component that injects multiple sibling children around the slotted child. Radix `Slot` expects a single valid child and can cause a browser runtime blank page. For sidebar navigation, use a real single-child `Link` component or a button with React Router `useNavigate()`.

- `2026-06-29_2137-project-state-docs`: When changing code, config layout, runtime behavior, dependencies, CLI commands, WebUI routes, or frontend structure, explicitly check whether `README.md`, `docs/README.md`, `docs/maa-runtime.md`, `docs/architecture-direction.md`, `.codex/project-history.md`, `.codex/project-lessons.md`, and the current session file need updates. This project relies on those files as active handoff state, not passive notes.

- `2026-06-29_2137-project-state-docs`: The project is still early-stage. For redesigns or upgrades, prefer simplifying the architecture and deleting obsolete functionality over preserving old behavior as fallback. Keep fallback paths only when there is a concrete current operational reason.

- `2026-06-30_0014-task-editor-fixes`: When splitting frontend JSON editor templates, update the template aggregation/import code and verify all schema enum forms are still routed to custom renderers. `oneOf`/`const` titled options require `isOneOfEnumControl`; otherwise the intended select renderer may not apply even though TypeScript builds.
