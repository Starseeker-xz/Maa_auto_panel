# Project Lessons

- `2026-06-26_1727-webui-config-runner`: With the currently resolved FastAPI/Starlette versions, `fastapi.testclient.TestClient` fails unless the extra `httpx2` package is installed. For now, verify the WebUI with a real `uvicorn` server plus `curl`, or intentionally add the test dependency before writing TestClient-based tests.

- `2026-06-29_1929-shadcn-sidebar`: In local shadcn/Radix wrappers, do not use `Slot`/`asChild` in a component that injects multiple sibling children around the slotted child. Radix `Slot` expects a single valid child and can cause a browser runtime blank page. For sidebar navigation, use a real single-child `Link` component or a button with React Router `useNavigate()`.
