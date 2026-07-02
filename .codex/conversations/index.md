# Conversation Index

- `2026-06-26_1620-maa-cli-framework-docs`: Initial project state setup, environment probing, PVE topology memory, and MAA documentation mirroring/reading for future maa-cli framework design.
- `2026-06-26_1702-setup-maa-cli-test`: Installed project-local `maa-cli`/MaaCore runtime, converted uploaded Windows GUI `test` basics into maa-cli profile/task config, and started first real `test` run.

- `2026-06-26_1727-webui-config-runner`: Started minimal WebUI/config-runner/src-organization task.

- `2026-06-26_2030-separate-frontend`: Separate the simple WebUI into the planned React/Vite frontend and reshape the UI around task list, config center, and maa-cli info logs.

- `2026-06-29_1929-shadcn-sidebar`: Replace the Mantine frontend pass with shadcn-style local components and clean Mantine out fully.

- `2026-06-29_2137-project-state-docs`: Inspect current repository state and refresh concise project history/documentation handoff records.

- `2026-06-29_2232-config-editing`: Implement backend task-config validation and parsed config API; add JSON Forms based frontend task editor, metadata fields, schema-drift/fallback editing UI, and left-pane edit/drag affordance.

- `2026-06-30_0014-task-editor-fixes`: Fix task editor metadata semantics, drag ordering UX, checkbox/tooltip styling, dependency logic, and enum labels.

- `2026-06-30_0124-config-save-delete`: Implement backend-backed config saving/reset/delete from the main page, fix route lock/sidebar spacing, and add/refine parallel settings panels for framework timezone/theme, default Profile, maa-cli/resource settings, maintenance actions, tooltips, and resource/update-info semantics.
- `2026-06-30_1626-maa-stage-candidates`: Implement MAA GUI-style Fight stage candidates, managed task-param placeholders, dynamic Fight/Infrast option APIs, and frontend managed array/dropdown rendering.
- `2026-06-30_1743-fix-infrast-plan-select`: Investigate and fix Infrast plan dropdown label not updating immediately after selecting an API-provided option.
- `2026-06-30_1752-maa-cli-sequential-analysis`: Read local runner and upstream maa-cli source to compare one full custom-task invocation with one-child-per-invocation orchestration.

- `2026-06-30_1934-scheduled-retry-architecture`: Implement retry_even_success metadata support, inspect current code for scheduled execution/retry architecture, and make low-risk architecture cleanup.
- `2026-06-30_2056-scheduled-execution`: Audit existing architecture/code before implementing scheduled execution, then build the scheduler domain/API/UI described in `TEMP/定时执行功能.md`.
- `2026-06-30_2318-gpu-ocr-research`: Investigate and test MaaCore GPU OCR availability in the current Linux MAA runtime, with Docker packaging notes.
- `2026-06-30_2342-full-project-audit`: Full backend/frontend/project-history audit execution. Added Chinese root audit reports, split backend routes/services, consolidated shared helpers, refactored frontend shared fields/polling/schedule panes, and cleaned large old scratch artifacts.

- `2026-07-01_1312-explain-log-flow`: Explain current log translation, chunking, and frontend response/display flow.
- `2026-07-01_1506-sse-log-delta`: Continue log SSE work by moving from full-state SSE payloads toward one full snapshot fetch plus incremental event pushes, while recording the project execution policy.
- `2026-07-01_2153-manage-service-history`: Stop the current WebUI process without manual PID searching, add temporary systemd management, replace SQLite scheduler state with readable state files, split framework diagnostics from runtime state, and restart the WebUI service.
- `2026-07-02_1933-config-sync-ui-schema`: Investigate frontend/backend task config synchronization and whether deprecated task editor schema UI fields can be removed safely.
