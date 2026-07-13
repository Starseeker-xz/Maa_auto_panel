# audit-exceptions-deps 子代理审计

- 父会话：`2026-07-13_1500-audit-run-architecture`
- 范围：只读核查通用运行层的路径依赖，以及 FastAPI 路由异常映射。
- 未修改项目代码，未运行测试（本任务为静态审计）。

## 1. 通用层依赖 `MaaRuntime`

### 结论

**Confirmed：问题成立。** `MaaRuntime` 是 `ApplicationPaths`、`FrameworkPaths`、`CachePaths`、`MaaInstallation` 和 `PathReferenceResolver` 的聚合门面（`maa/runtime.py:10-33`），composition root 先创建它，再把同一聚合对象传给几乎所有服务（`web/services.py:115-169`）。这使通用 store、diagnostics、process runner 都能看见 MAA 安装路径及不相关路径。

当前实际构造方向：

```text
create_services
  -> MaaRuntime
       -> PathLayout
            -> ApplicationPaths
            -> FrameworkPaths
            -> CachePaths
            -> MaaInstallation
       -> PathReferenceResolver(framework, runtime, cache)
  -> Diagnostics(MaaRuntime)
  -> RunStateStore(MaaRuntime)
  -> MaaRunManager / SchedulerService / MaintenanceActionManager / ToolRunManager
       -> GenericRunManager(MaaRuntime, shared store, shared diagnostics, coordinator)
            -> run_streaming_process(MaaRuntime, cmd, env=...)
                 -> subprocess.Popen(cwd=MaaRuntime.repo_root, env=...)
```

证据及最小实际需求：

- `GenericRunManager.__init__` 接收并保存 `MaaRuntime`，还允许隐式构造 store/diagnostics（`run_manager/manager.py:251-265`）。整个类对 `self.runtime` 的唯一功能性使用是把它传给 `run_streaming_process`（`:469-501`）；后者只读取 `runtime.repo_root` 作为 `Popen.cwd`（`process.py:35-64`）。因此 manager 实际只缺一个 process cwd/process executor，不需要任何 MAA 路径。
- `RunStateStore` 只需要 framework run-state/run-history 两组目录、framework logical-reference resolver 和 framework root（`run_manager/store.py:63-80, 280-318, 438, 462, 475-479`）。它不使用 MAA binary/env/cache/application paths。
- `Diagnostics` 的事件、framework、maa-cli、tool、script、MAACore capture **目标目录** 都在 framework debug tree，引用编码也只用 `framework` root（`diagnostics.py:38-159, 190`）。但它还承担了 MAA 安装目录清理和 MAACore 源日志读取：`generated_config_dir`、`run_log_dir`、`state_home/maa/debug`（`:220-252`）。所以不能只改构造参数；必须先把这三个 MAA 特有的 retention/source-log 职责移到 MAA 边界，否则所谓 `Diagnostics(FrameworkPaths, resolver)` 只是隐藏依赖。
- `MaaRuntime.env()` 拼装 PATH、MAA_CONFIG_DIR、XDG_*（`maa/runtime.py:147-155`），这是 MAA process context，不应进入通用 process runner。

### 建议的目标签名

保持单一 run 状态机和锁所有权，不拆 manager；只收窄协作者：

```python
def run_streaming_process(
    cmd: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    ...,
) -> StreamingProcessResult: ...

class GenericRunManager:
    def __init__(
        self,
        store: RunStateStore,
        diagnostics: Diagnostics,
        coordinator: RunCoordinator,
        *,
        process_cwd: Path,
        on_run_finished: RunFinishedListener | None = None,
        resource_wait_timeout_seconds: Callable[[], float] | None = None,
    ) -> None: ...

class RunStateStore:
    def __init__(
        self,
        paths: FrameworkPaths,
        references: PathReferenceResolver,
        retention: StateRetentionPolicy | None = None,
    ) -> None: ...

class Diagnostics:
    def __init__(
        self,
        paths: FrameworkPaths,
        references: PathReferenceResolver,
        retention: LogRetentionPolicy | None = None,
    ) -> None: ...
```

更彻底且仍属实现协作者的方案，是让 `CommandSpec` 增加明确的 `cwd: Path`，随后 `GenericRunManager` 连 `process_cwd` 都不需要；manager 只把 `CommandSpec.cmd/cwd/env` 交给 executor。这最符合“process executor 仅依赖 command/cwd/env”，也避免未来不同工具误用 repo root。若所有命令当前都以 application root 为 cwd，可在各领域 plan builder 或 composition root 明确填入 `application.root`。

建议移出 `Diagnostics` 的 MAA 特有部分：

- `maacore_log_offset`、`capture_maacore_log` 的源文件访问；
- `generated_config_dir`、legacy `run_log_dir`、MAACore debug retention。

可放进 `maa/log_capture.py` 一类小协作者，例如 `MaaLogCapture(installation: MaaInstallation, diagnostics: Diagnostics)`；目标 capture 文件仍由 `Diagnostics` 管，MAA 源文件只由 MAA 协作者读取。不要再造一个 manager。

### composition root 改法

`create_services` 应先显式构造 layout 和 resolver，而不是先造 MaaRuntime 聚合门面：

```python
layout = PathLayout.create(app_root, data_root=data_root, cache_root=cache_root)
references = PathReferenceResolver({
    "framework": layout.framework.root,
    "runtime": layout.maa.root.parent,
    "cache": layout.cache.root,
})
diagnostics = Diagnostics(layout.framework, references)
run_state = RunStateStore(layout.framework, references)
maa_process = MaaProcessContext(layout.maa)  # 负责 env；名称可再定
```

然后按边界传参：frontend/schema 用 `ApplicationPaths`，游戏下载用 `CachePaths`，通用 run manager 用显式 store/diagnostics/coordinator 与 command cwd，MAA runner/maintenance/MAA log capture 用 `MaaInstallation`（以及必要的 application cwd）。同时删除 `GenericRunManager`、各领域 manager 中 `store or RunStateStore(runtime)` / `diagnostics or Diagnostics(runtime)` 这类 fallback；composition root 已存在，继续保留 fallback 会形成第二套隐式装配路径并掩盖依赖回流。测试使用小 fixture 显式装配即可。

建议分阶段：

1. 先改 `process.py` + `CommandSpec`/manager 调用边界，移除 `GenericRunManager -> MaaRuntime`（低风险、调用点清晰）。
2. 给 `FrameworkPaths` 增加 `framework_state_dir/run_state_dir/framework_history_dir/run_history_dir/framework_log_dir/...` 等派生属性，把 store/diagnostics 改为显式依赖并更新 composition root。
3. 最后抽出 MAA log capture/retention，再删除或大幅收窄 `MaaRuntime`。一次聚焦一个边界，避免全库同时改构造签名。

## 2. FastAPI 异常模型

### 现状统计

**Confirmed：问题成立。** 在 `web/routes/*.py` 加共享 `run_manager/router.py` 中，共有 **39 处**显式 400/404/409：

- 400：18 处，全部来自 `except ValueError`。
- 404：16 处，其中 9 处 `FileNotFoundError`、5 处 `KeyError`、2 处 `None` 棐查后直接抛 `HTTPException`。
- 409：5 处，全部来自 `except RuntimeError`。

集中证据：

- configs：`web/routes/configs.py:40-43, 50-53, 59-62`
- history：`web/routes/history.py:24-27, 41-44`
- MAA lookup：`web/routes/maa.py:15-33`
- maintenance：`web/routes/maintenance.py:27-43`
- manual runs：`web/routes/runs.py:29-43`
- schedules：`web/routes/schedules.py:33-46, 57-94`
- settings：`web/routes/settings.py:33-39, 41-58`
- tools：`web/routes/tools.py:36-42`
- 共享 run control：`run_manager/router.py:54-95`

当前仅有少量自定义异常：

- `ConfigValidationFailure(ValueError)`，携带结构化 validation result，路由转换为 422（`config/manager.py:38-42`, `web/responses.py:8-17`）。
- `RunConflictError(RuntimeError)`、`RunResourceTimeoutError`、`RunResourceCancelledError(RuntimeError)`（`run_manager/coordinator.py:45-67`）。资源冲突发生在 manager 后台执行线程内并被转换成 run 结果/事件（`run_manager/manager.py:561-575`），它与“HTTP start 请求同步返回 409”不是同一边界，不应为了统一 handler 强行改变异步语义。

### 五类异常是否合适

少量领域异常 + FastAPI handlers 的方向合适，五类基本覆盖当前问题，但必须按**语义边界**抛出，不能注册 `ValueError/FileNotFoundError/KeyError/RuntimeError` 的全局 handler。

- `InvalidRequest` -> 400：适用于 Pydantic 之后的业务输入错误，例如未知 maintenance/tool kind、非法 config/schedule 名称、非法路径引用、非法 timezone。不要把任意 `ValueError` 转 400；JSON 解码、内部类型假设、第三方库 ValueError 可能是服务端缺陷。
- `ResourceNotFound` -> 404：适用于按用户标识查找不到 config/task/profile/schedule/run。应在 repository/service 边界把“确认是用户资源缺失”的 `FileNotFoundError`/`KeyError` 转换掉。不要全局映射 FileNotFoundError，因为缺少 MAA binary、内部 schema、权限竞争下文件消失不是同一种 404。
- `Conflict` -> 409：适用于已有 active run、删除活动 run、不可兼容的资源状态。`Application is shutting down` 更像 `RuntimeUnavailable`/503，而不是 409。现有 coordinator conflict 若仍只在后台形成失败 run，可以保留专用内部异常或令其继承 `Conflict`，但不要因此承诺 HTTP 409。
- `CorruptState` -> 500（响应使用稳定、非敏感 detail，并记录原异常）：适用于 durable framework state/config 格式损坏。当前 `read_json_object` 在 JSONDecodeError 或非-object 时静默返回 `{}`（`storage/files.py:41-49`），`read_jsonl` 也跳过 malformed 行（`:24-38`）；在接 handler 前必须先让“缺失”和“损坏”可区分，否则 `CorruptState` 永远不会出现且损坏可能被下一次写入覆盖。JSONL 对 append-only 日志可继续容错，但状态索引不宜静默清空。
- `RuntimeUnavailable` -> 503：适用于关闭中、所需 runtime/binary 不存在或无法启动、必要外部运行环境不可用。注意当前 process launch 在线程内发生，API 可能已返回一个 run，随后 run 被标为 failed；若希望 start API 返回 503，需要在领域 runner 创建 run record 前做明确、无竞争副作用的 preflight。普通子进程非零退出仍应是 run failure，不是 HTTP 异常。

`ConfigValidationFailure` 是现有重要边界，不能丢掉结构化 422。可选做法：保留它作为独立、小型异常并配置专门 handler；或者让它继承 `InvalidRequest`，但专用 422 handler 必须比通用 400 handler 更具体。FastAPI/Pydantic 自带的 request validation 422 也应保持不变。

### handlers 与迁移建议

建议在非 web 模块（如 `errors.py`）定义五类异常，避免领域层导入 FastAPI。异常至少携带稳定 message；如前端需要机器可读分支，可使用固定 `code`，不要直接泄露底层 OSError/path。

在 `web/app.py:create_app` 注册 5 个 handler（以及 `ConfigValidationFailure` 422 handler），统一返回当前兼容的 `{"detail": ...}` 或一次性定义稳定 envelope。建议映射为 400/404/409/500/503。5xx handler 应记录 cause/context；当前 request middleware 在异常已被 FastAPI handler 转成 response 后未必进入 `except` 日志路径，因此不能只依赖 `web/app.py:47-79` 的 middleware 记录 `CorruptState`/`RuntimeUnavailable`。

迁移顺序应从抛出点开始，而不是先删 route catches：

1. 定义异常与 handlers，补 handler 响应测试。
2. 每次迁移一个服务边界：将明确的 built-in 转换为领域异常，并删除对应 route try/except。
3. 最后收敛共享 `run_manager/router.py` 的 KeyError/None 语义，使 manager API 对不存在统一抛 `ResourceNotFound`（或统一返回 None 后由一个 web helper 处理，二者择一，不要混用）。
4. 保留真正的编程错误为 500，验证未知 ValueError/RuntimeError 不再被误报成客户端错误。

## 3. 项目级易复发陷阱

1. **聚合路径对象的便利性会持续造成依赖回流。** 只要 `MaaRuntime` 仍被用作所有构造器的首参，新服务很容易顺手读取任意路径。安全默认是 composition root 解包后只传窄类型，并删除内部 fallback 装配。
2. **`Diagnostics` 名称掩盖了 MAA ownership。** 日志目标在 framework tree 不代表日志源和清理对象也是 framework-owned；MAACore source、generated configs、legacy MAA run logs 必须留在 MAA 边界。
3. **不要按 Python 异常类型全局决定 HTTP 状态。** 同一个 `FileNotFoundError` 既可能是用户资源 404，也可能是 runtime/schema 缺失 503/500；同一个 `RuntimeError` 既可能是 409，也可能是 shutdown 503 或 bug 500。
4. **静默 JSON 恢复会破坏 `CorruptState` 模型。** durable state 读取失败返回 `{}` 会把损坏伪装成“无数据”，并有被覆盖的风险。缺失、损坏、暂时 I/O 失败必须分开处理。
5. **同步 HTTP conflict 与后台 run conflict 不应混为一谈。** coordinator 的资源冲突目前是已接受 run 的终态/事件；若未来要改成请求时 409，需要显式改变 API 生命周期契约并处理 acquire 与启动之间的竞态。
