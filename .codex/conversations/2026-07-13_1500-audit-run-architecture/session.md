# Session `2026-07-13_1500-audit-run-architecture`

## Scope

- 先只读审计 `GenericRunManager` 职责、通用层对 `MaaRuntime` 的依赖，以及 FastAPI 异常映射；随后按用户授权实施对应重构。
- 按用户建议分派子代理 `audit-exceptions-deps`；其完整报告见同目录 `audit-exceptions-deps.md`。
- 审计阶段未改业务代码；实施阶段已修改后端、测试与 `docs/BACKEND_AUDIT.md`。

## Verification

- `wc -l`：`run_manager/manager.py` 1043 行；其中同时包含 plan/callback DTO、单一状态机与锁、thread/process 控制、retry loop、resource acquire、script hooks、diagnostics/event、store/retention/final listener 编排。
- `GenericRunManager` 对 `MaaRuntime` 的唯一功能性使用是传入 `run_streaming_process`；process 层只读取 `runtime.repo_root` 作为 `Popen.cwd`。
- `RunStateStore` 实际只需 framework state/history paths 与 `PathReferenceResolver`。
- `Diagnostics` 目标日志大多在 framework tree，但仍读取/清理 `MaaInstallation` 的 `generated_config_dir`、`run_log_dir`、`state_home/maa/debug`；必须先迁移 MAA-specific source/retention 才能真实解耦。
- routes 与共享 `run_manager/router.py` 共 39 处显式 400/404/409：400=18、404=16、409=5。
- `storage/files.py:read_json_object` 对 malformed JSON / 非 object 静默返回 `{}`，使 durable state 损坏可能被后续写入覆盖；这是 `CorruptState` 生效前的阻塞问题。
- 定向基线：`.venv/bin/python -m pytest -q tests/test_run_manager.py tests/test_run_manager_command.py tests/test_run_state_and_diagnostics.py` -> `17 passed in 1.40s`。

## Intermediate findings

- 建议保留 `GenericRunManager` 对单一锁、condition、live state、retry loop、状态转换、资源 acquire 顺序和 stop/force-stop 决策的所有权；不要拆多个 manager，也不要把 retry loop 交给领域 callbacks。
- 可拆的实现协作者/类型边界：plan/decision DTO 模块、显式 `CommandSpec(cmd, cwd, env, output_log_file)` + streaming executor、无状态 script-hook executor、MAA log capture/retention collaborator。协作者不得直接突变 `LiveRun`。
- `start()` 在持锁区调用 `store.create_run`；`stop()`/`force_stop()` 在持锁区写 framework diagnostics，存在文件 I/O 阻塞 manager condition 的风险。
- run 先写入 `_runs`，随后在锁外绑定并启动 thread，shutdown/join 有窄竞态窗口；需要并发 characterization test 后再调整发布顺序。
- `_finish_run` 先把 live state 标终态，再持久化；若持久化失败，外层 generic failure path 无法再次 finalize。后续实现需明确 persistence failure policy，而不只是搬函数。
- 五类应用异常方向成立：`InvalidRequest` 400、`ResourceNotFound` 404、`Conflict` 409、`CorruptState` 500、`RuntimeUnavailable` 503。保留 `ConfigValidationFailure` 结构化 422；绝不能为 Python builtins 注册全局 HTTP handlers。
- coordinator 的后台资源冲突维持“accepted run -> failed terminal/event”语义，不应自动变成同步 HTTP 409；若要 503 runtime preflight，必须在 run 建档前明确检查。
- 用户补充确认：`GenericRunManager` 不应包含任何运行分类的专项语义。所谓 MAA log capture 只能是 `maa/` 领域内的实现（更准确命名为 `MaaCoreLogCapture` 或局部函数），由 MAA runner/scheduler callbacks 使用，绝不注入或暴露给 `GenericRunManager`。generated-config、legacy run-log retention 也不应被笼统塞进该 capture 协作者，应分别按 artifact ownership、MAA installation cleanup 处理或删除无价值旧路径。
- 实施可有限并行：process/manager 通用边界与应用异常/route 迁移可由不同工作流并行；composition root、共享构造签名、diagnostics/store 收窄存在高重叠，应由主线串行集成，避免共享工作区冲突。

## Session mistake

- 一条 `rg` 命令因复杂正则中的双引号嵌套破坏 shell quoting 而语法失败；未产生项目副作用。已改用单引号包裹完整正则，并将通用教训加入 `/root/.codex/lessons.md`。

## Environment effects

- 新增本 session 目录与记录。
- 更新 `/root/.codex/lessons.md`，加入复杂 `rg` 正则 shell quoting 的安全默认；该效果对未来会话持续有效。

## Implementation outcome

- 用户随后授权实施，并要求把 MaaCore log 捕捉改为 Diagnostics 的通用“输入文件路径 + offset，保存增量日志”操作；并明确正常语义为每个实际执行 retry 捕捉一次。
- 并行子任务：`run-core`、`exception-model`、`incremental-diagnostics`，记录分别在同目录对应 markdown；主线完成构造、路径、route 与测试整合。
- 新增 `run_manager/contracts.py`；`GenericRunManager` 从 1043 行降至约 920 行，仍唯一拥有状态机/锁/retry/resource/stop/finalize，且源码无任何运行分类专项语义。
- `CommandSpec` 现显式要求 cwd；`run_streaming_process` 只依赖 cmd/cwd/env；GenericRunManager 删除 MaaRuntime 与 store/diagnostics fallback。
- RunStateStore、Diagnostics 构造收窄为 FrameworkPaths + PathReferenceResolver。Diagnostics 新增 `IncrementalLogCapture` 与 `capture_file_increment`，保存原始 bytes；MAA callback 管理 MaaCore source/offset。artifact role 从 `maacore_log_file` 泛化为 `diagnostic_log_file`。
- Diagnostics 删除 MAA source、generated-config、legacy run-log 专项 retention；generated config 继续由 run-owned artifact retention 管理。MAA domain 仍接收 MaaRuntime aggregate，进一步收窄到 MaaInstallation/process context 是独立后续边界。
- 新增五类应用异常与统一 handlers；routes/shared router 原 39 处 builtin HTTP 映射已删除。durable JSON、config、schedule 损坏抛 CorruptState；测试确认损坏 run index 不被 create 覆写。
- manager thread 现在线程成功启动后才对锁外观察者可见；stop/force-stop 的 diagnostics 文件 I/O 移出 manager lock，并在锁内快照 process handle。
- 最终验证：完整后端测试多次为 `110 passed`（最近一次 6.27s）；compileall passed；`git diff --check` passed。
