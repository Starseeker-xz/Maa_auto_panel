# run-core 子任务记录

父会话：`2026-07-13_1500-audit-run-architecture`

## 已实施

- `CommandSpec` 现在显式包含必填 `cwd: Path`，与 `cmd`、`env`、可选 `output_log_file` 一起构成完整的进程输入。
- `run_streaming_process` 删除 `MaaRuntime` 参数，改为只接收 `cmd`、`cwd`、`env` 及进程控制 callbacks/timeouts。
- `GenericRunManager` 删除 `MaaRuntime` import、构造参数和 `self.runtime`。
- `GenericRunManager` 的 `store`、`diagnostics` 改为必填注入，删除内部 `RunStateStore(runtime)` / `Diagnostics(runtime)` fallback；`coordinator` 仍保留通用默认实例。
- manager 内部 `run_process` 直接接收完整 `CommandSpec`；主命令与 script hook 走同一通用执行边界，状态机、锁、retry loop 和 hook 时序未拆分、未引入分类专项分支。

## 测试与检查

- 初始直接执行 `pytest` 失败：当前 shell PATH 没有 pytest。依据项目 lesson 改用 `.venv/bin/python -m pytest`。
- `.venv/bin/python -m pytest -q tests/test_process.py tests/test_run_manager_command.py`：`9 passed in 3.61s`。
- 新增显式 cwd 行为测试：子进程观察到的 `Path.cwd()` 必须等于调用方传入目录。
- `.venv/bin/python -m compileall -q` 对三个负责的源文件通过。
- `git diff --check` 对负责源文件及直接测试通过。
- ruff 未运行：现有 `.venv` 未安装 ruff（`No module named ruff`）。

## 整合提醒 / 耐久结论

- `CommandSpec.cwd` 必须保持必填，避免通用层重新从 runtime aggregate 猜测 cwd；领域 command builder 或 composition root 应明确选择工作目录。
- manager 构造签名现在是 `GenericRunManager(store, diagnostics, coordinator=None, ...)`。所有领域 manager、composition root 和旧测试调用点必须同步删除首个 runtime 参数。
- 共享工作区中 `RunStateStore` 已被并行改为 `RunStateStore(FrameworkPaths, PathReferenceResolver, ...)`；测试 helper 也应按此装配，不能继续传 `MaaRuntime`。
- `tests/test_backend_utilities.py` 中直接 process 测试已迁移，但该文件仍有两处 `CommandSpec` 和一个 manager 构造调用需要父代理在整合领域调用点时更新。
- 易复发项目陷阱：`.venv/bin/pytest` 的 console-script 路径可能失效或 PATH 中不存在 pytest；本仓库验证优先使用 `.venv/bin/python -m pytest`。
