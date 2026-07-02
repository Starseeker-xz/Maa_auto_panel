# Session 2026-07-02_1933-config-sync-ui-schema

## Task

- User asked how frontend/backend task config synchronization currently works, and whether deprecated UI fields can simply be deleted from `frontend/src/config/task-editor-schemas` without causing missing behavior, warnings, or dead code.

## Notes

- No business code changes.
- Confirmed current config sync path:
  - Backend `GET /api/configs/tasks/{name}` returns parsed `data`, editable `task_items`, validation, and metadata schema.
  - Frontend `MainPage` stores local task item drafts; `ConfigEditorPane` edits `params` with JSON Forms and `linux_maa` metadata separately.
  - Save sends `{ data, task_items }` to `PUT /api/configs/tasks/{name}`.
  - Backend converts task items back to maa-cli config with `task_items_to_config_data()`, validates, and writes TOML/JSON.
- Confirmed `frontend/src/config/task-editor-schemas/*.json` is frontend-only visual/editor schema. Backend validation does not import it.
- Current deprecated visual fields found:
  - `Fight.expiring_medicine`
  - `Recruit.skip_robot`
- Removing a deprecated field only from `advanced` hides it from UI while preserving existing values in `params`.
- Removing the schema property too is build-safe if the UI key is also removed, because templates allow `additionalProperties` and backend maa-cli task schema accepts arbitrary task param keys matching `[a-zA-Z0-9_]+`.
- Removing only the property while leaving it in `general`/`advanced` leaves a dangling JSON Forms control scope and may render a strange fallback control; avoid this.
- Hiding these fields will not automatically delete old values from saved configs. Existing old params can round-trip through drafts and saves unless a cleanup/migration is added.
