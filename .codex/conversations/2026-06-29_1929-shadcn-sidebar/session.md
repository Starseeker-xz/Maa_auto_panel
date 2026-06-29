# Session 2026-06-29_1929-shadcn-sidebar

## Task

- Remove Mantine fully after the experiment.
- Rebuild the frontend UI using shadcn-style local React components, Radix primitives, Tailwind utilities, and an expandable/collapsible sidebar.


## Environment Effects

- Upgraded Node using `npm install -g n && n 22`; active Node is expected to be 22.x from `/usr/local/bin/node`. This was done to use the current shadcn/Tailwind v4 path instead of downgrading frontend tooling for Debian Node 18.

## Outcome

- Removed Mantine dependencies (`@mantine/core`, `@mantine/hooks`) and replaced the UI with shadcn-style local components under `frontend/src/components/ui/`.
- Added `components.json`, `frontend/src/lib/utils.ts`, Radix primitive dependencies, Tailwind v4, `@tailwindcss/vite`, and `tw-animate-css`.
- Configured Vite `@` alias for `frontend/src`.
- Rebuilt the expandable/collapsible sidebar using local shadcn-style `SidebarProvider`, `Sidebar`, `SidebarInset`, and `SidebarMenuButton` components instead of Mantine AppShell/NavLink.
- Verification: `rg` found no Mantine references outside ignored build/dependency folders; `npm run build`, `uv run python -m compileall src`, `GET /`, and latest asset fetch succeeded.

## Page Split

- Split `frontend/src/main.tsx` into `App.tsx`, `pages/MainPage.tsx`, `pages/SchedulePage.tsx`, `pages/SettingsPage.tsx`, `lib/api.ts`, `lib/types.ts`, and `lib/logs.ts`.
- `main.tsx` now only mounts React and imports global CSS.
- Verification: `npm run build`, `GET /`, and latest built asset fetch succeeded.

## React Router Split

- Added `react-router-dom`.
- Replaced manual page state with React Router routes: `/`, `/tasks/:taskConfig`, `/tasks/:taskConfig/items/:itemIndex`, `/schedule`, and `/settings`.
- Split the main page's three columns into `pages/main/TaskListPane.tsx`, `pages/main/ConfigEditorPane.tsx`, and `pages/main/LogPane.tsx`.
- Task config selection now navigates to `/tasks/<config>`.
- Task gear links navigate to `/tasks/<config>/items/<itemIndex>`; the center pane uses this URL param to show the selected subtask placeholder.
- Verification: `npm run build`, `uv run python -m compileall src`, latest asset fetch, and HTTP 200 checks for `/`, `/tasks/test`, `/tasks/test/items/1`, `/schedule`, and `/settings` succeeded.

## Runtime Fixes

- User reported blank pages after React Router split. Root cause was likely `SidebarMenuButton asChild` rendering Radix `Slot` with multiple children (icon span plus label span), which can throw a browser runtime error and blank the React tree.
- Fixed by removing `asChild` usage from sidebar navigation and using `useNavigate()` button handlers instead. React Router still owns the routes and URL changes.
- Verification: `npm run build`, `GET /schedule`, latest built asset fetch, and `uv run python -m compileall src` succeeded. No local Chromium/Chrome binary was available for a browser-render screenshot.

## Task Item URL IDs

- Replaced subtask URL route variable from `itemIndex` to `taskItemId` because list indexes are unstable under drag reorder.
- Backend `ConfigManager.read_task_items()` now returns `id` for each task item. Explicit task `id` is used if present; otherwise an id is generated from task type plus SHA-1 hash of canonicalized task content.
- Current generated ids are stable across reordering but change if task content changes. Long term, editable framework-owned configs should persist explicit per-task ids if URLs must survive edits.
- Restarted active WebUI after backend code change. Active process is now `49415` on port `8000`.
- Verification: `npm run build`, `uv run python -m compileall src`, `GET /api/configs/tasks/test`, and SPA route checks succeeded.

## Config Split And Framework Metadata

- Moved editable MAA/framework config out of `runtime/maa/config` into `config/maa`. Current files were copied to `config/maa/profiles`, `config/maa/tasks`, and `config/maa/infrast`.
- `MaaRuntime.config_dir` and `scripts/maa-env` now point to `config/maa`.
- Added `[tasks.linux_maa] id = ...` to each task in `config/maa/tasks/test.toml`. API task items now return both `id` and `linux_maa` metadata.
- Confirmed raw `maa-cli run test` rejects unknown `linux_maa` fields. Implemented sanitized temporary config generation under `runtime/maa/generated-configs/<run-id>/`: task files are JSON with `linux_maa` stripped, and non-`tasks` config subdirectories such as `profiles` and `infrast` are symlinked into the generated config root.
- Confirmed sanitized generated config dry-run succeeds for `test`.
- Restarted active WebUI. Active process is now `58210` on port `8000`.
- Verification: `scripts/maa-env maa list`, `uv run python -m compileall src`, `npm run build`, `GET /api/configs`, `GET /api/configs/tasks/test`, and `GET /` succeeded.

## Session Mistakes

- Used `pkill -f linux-maa webui` inside a command string that also contained that pattern, which matched the current shell command and interrupted the restart. Use exact PIDs from `pgrep -af` instead.
