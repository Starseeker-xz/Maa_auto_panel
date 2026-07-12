# backend-retention

## 结论与实现

- Confirmed：原 P1 成立。`GenericRunManager._runs/_plans` 会永久保留终态状态和 callbacks；run/retry index 独立截断会留下 history/diagnostics/artifact orphan，也可能产生仍保留历史但 retry index 已丢失的悬空状态。
- manager 现在终态立即移除 plan/callback，只保留最近终态 live snapshot，到下一次运行时丢弃；历史显式删除通过 `discard_terminal_run` 同步清理各 manager snapshot。
- `RunStateStore.enforce_retention()` 以 run 为淘汰单元，active run 始终保留，run/retry 两个上限共同决定终态 run 是否保留；不再在各自写入时静默截断。
- 淘汰或显式删除级联删除 history、event/stdout/stderr diagnostics，以及白名单声明为 owned 的 `generated_config_dir`、`maacore_log_file`。未知/shared/external artifact 不删除。
- `Diagnostics.enforce_retention(protected_paths=...)` 保护仍被 run store 引用的路径，并删除没有 owner 的 run diagnostics/artifacts；独立调用仍保留旧的 age/count 行为。
- 同秒创建的 run 会发生 ISO 秒级时间戳并列；`_upsert_run` 现将本次 touched record 放首位，以保证稳定排序不会误淘汰刚创建的 run。

## 修改文件

- `src/maa_auto_panel/run_manager/manager.py`
- `src/maa_auto_panel/run_manager/store.py`
- `src/maa_auto_panel/diagnostics.py`
- `src/maa_auto_panel/web/services.py`
- `src/maa_auto_panel/web/routes/history.py`
- `tests/test_run_manager.py`
- `tests/test_run_state_and_diagnostics.py`
- `docs/BACKEND_AUDIT.md`

## 验证

- `.venv/bin/python -m pytest -q tests/test_run_state_and_diagnostics.py tests/test_run_manager.py tests/test_backend_utilities.py tests/test_shutdown.py`：32 passed。
- `.venv/bin/python -m pytest -q`：101 passed。
- `.venv/bin/python -m compileall -q src tests`：通过。
- `git diff --check`：通过。
- 直接执行 `pytest` 失败（PATH 无 pytest）；按项目 lesson 改用 `.venv/bin/python -m pytest`。

## 未来容易复发的项目级陷阱

- retention 必须以 run 为 ownership 单元，不应在 run/retry/diagnostics 各层独立截断；否则会制造引用悬空或 orphan。
- artifact 级联删除必须由明确角色表达 ownership，不能递归扫描任意 metadata/path 字符串。
- `server_now_iso()` 只有秒精度；任何依赖新旧顺序的逻辑必须保留稳定插入顺序，不能假设 timestamp 唯一。
