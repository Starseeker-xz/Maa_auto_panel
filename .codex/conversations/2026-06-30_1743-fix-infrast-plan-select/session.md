# Session 2026-06-30_1743-fix-infrast-plan-select

- Started: 2026-06-30 17:43 UTC.
- Task: Fix Infrast dynamic plan dropdown text not updating immediately after selecting an API-provided option.
- Observed likely cause: runtime-value dynamic select called JSON Forms handleChange, then immediately updated managed metadata; parent item update with stale params could reset local params before the select label reflected the new value.
- Attempted first fix: reordered runtime-value metadata update before JSON Forms handleChange. Browser verification still reproduced the stale label, so this was not sufficient.
- Final change: runtime-value dynamic selects now use a dedicated renderer config callback that updates params and managed metadata as one logical patch. ConfigEditorPane implements that callback by updating local params, local metadata, and the selected task item patch together.
- Verification: npm run build passed in frontend; Vite reported only the existing large chunk warning.
- Verification: Playwright opened http://127.0.0.1:8000/tasks/test/items/infrast-37153e4c, selected the exact "中途切换" plan option, and confirmed the 基建计划 trigger text changed immediately from "休息（2）" to "中途切换".

- Follow-up: changed task item ids to be fixed identifiers. Removed backend sha1/content-digest id recomputation from ConfigManager; read-time ids now preserve linux_maa.id after slug normalization and only append -2/-3 when duplicates exist in the same task list. Frontend reindexTaskItems was renamed to withTaskItemIndexes to clarify it only maintains display order index.
- Verification: npm run build passed in frontend; uv run python -m compileall -q src/linux_maa/config/manager.py passed.
- Mistake: tried MaaRuntime.discover(), but MaaRuntime has no discover method. Use MaaRuntime(find_repo_root()) for direct ConfigManager checks.
- Verification: direct ConfigManager read of config/maa/tasks/test.toml returned ids matching linux_maa.id exactly: startup-a5ce8dac, award-8123686a, mall-7d4ad25c, infrast-37153e4c, fight-e6d4bc5d, recruit-d1901df5.
- Verification: duplicate-id in-memory check returned ['fixed-id', 'fixed-id-2', 'mall-c', 'mall-c-2'], confirming collisions are handled only within the list and no content hash is added.
