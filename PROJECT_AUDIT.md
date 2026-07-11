# Maa Auto Panel 全项目审计报告

审计日期：2026-07-10
审计对象：当前工作区完整代码与实际运行环境（含尚未提交的重命名/通用化改动）
审计会话：`2026-07-10_0416-full-project-audit`

## 1. 结论摘要

项目已经完成立项目标中的主要闭环：配置编辑、手动运行、定时执行、重试、日志结构化、历史记录、维护动作和工具运行均已可用。最近完成的 `GenericRunManager` 重构也确实消除了四类运行的大量生命周期重复，当前代码不是需要推倒重写的状态。

但项目距离“可长期运行、可安全暴露、可平滑接入其他 maa-cli 类工具和自定义脚本”的通用框架仍有明显差距。主要矛盾已经从功能缺失转为以下四项：

1. **运行时更新缺少互斥边界**：维护动作可以与正在运行的 MAA 流程并发修改同一运行时。应用镜像与 MAA runtime 应独立演进，runtime 保持为可在线更新的持久卷。
2. **进程生命周期仍不可靠**：流读取对无换行输出会阻塞，超时和停止可能失效；应用退出没有统一关闭调度器、运行线程和子进程。
3. **“通用层”仍依赖 MAA 运行时**：进程执行、运行管理、状态存储和诊断都接收 `MaaRuntime`，新 integration 会被迫依赖 MAA 路径布局。
4. **扩展点尚未形成产品模型**：自定义脚本只是 schedule restart hook；工具是硬编码字典；前端/API/历史筛选仍认识固定的 manual/schedule/tool/maintenance 类型。

建议先修运行与安全基线，再抽离框架上下文，随后建立内部 action/integration registry。现阶段不建议引入数据库、微服务或第三方插件加载器；这些会放大复杂度，却没有解决当前最关键的边界问题。

## 2. 审计范围与基线

### 2.1 代码规模

- 后端：`src/maa_auto_panel/`，约 50 个 Python 文件。
- 前端：`frontend/src/`，约 50 个 TypeScript/TSX/JSON/CSS 文件。
- 后端与前端相关源文件合计约 20,204 行。
- 后端最大文件：
  - `run_manager/manager.py`：894 行。
  - `maa/log_templates.py`：787 行。
  - `logs/pipeline.py`：673 行。
  - `scheduler/service.py`：652 行。
- 前端最大文件：
  - `SettingsPage.tsx`：713 行。
  - `SchedulePage.tsx`：583 行。
  - `MainPage.tsx`：447 行。
  - `types.ts`：479 行。

### 2.2 验证结果

| 检查 | 结果 |
|---|---|
| Ruff | 通过 |
| Python compileall | 通过 |
| Pytest | 66 passed |
| Vulture（80% confidence） | 无发现 |
| TypeScript + Vite build | 通过 |
| `git diff --check` | 通过 |
| `npm audit` | 0 个已知漏洞 |
| 前端产物 | JS 768.47 kB，gzip 244.73 kB；存在 >500 kB chunk warning |

测试入口存在一个环境问题：`.venv/bin/pytest` 的 shebang 仍指向重命名前的 `/root/Linux_maa/.venv/bin/python3`，因此 `uv run pytest` 无法启动；使用 `.venv/bin/python -m pytest` 时 66 个测试全部通过。`uv sync --dry-run` 还检测到旧安装元数据 `linux-maa==0.1.0`。

### 2.3 当前裸机测试状态

- systemd 服务正在运行，绑定 `0.0.0.0:8000`；这是便于开发测试的临时运行方式，不是目标生产部署模型。
- unit 使用 `User=root`，且默认 CLI host 也是 `0.0.0.0`。容器化后应重新按容器用户、capability、volume 和 publish port 评估，不能把宿主 root 风险原样套用到容器内 root。
- OpenAPI 中没有 security scheme。
- 当前有真实 scheduled MAA run；审计过程没有停止或修改它。
- 本地数据规模：`history/framework` 约 2.4 MB（44 个 history 文件），`debug/framework` 约 90 MB。
- 仓库中没有可复现的 systemd unit、Dockerfile、Compose、CI workflow 或前端测试配置。

## 3. 当前架构评价

### 3.1 值得保留的部分

以下设计已经形成稳定基础，应继续沿用：

- `LiveRun + LiveRetry + {run, retries}` 统一了手动、定时、工具、维护的状态和历史结构。
- `GenericRunManager` 统一管理启动、重试、停止、强停、日志、持久化与 resource coordinator，领域通过 callback 提供差异。
- 可见日志、原始外部进程日志、框架日志、运行状态分离，职责比早期实现清晰。
- `MaaTaskResultCollector` 与 UI 可见日志模板解耦，调度策略不再依赖展示文本。
- 配置文件与本地运行状态均使用可读文本，符合当前规模，也利于人工恢复。
- 文件名/path traversal 防护、原子文本写入、配置 schema 校验、回收站删除等基础措施是合理的。
- Run resource/priority 已有可扩展雏形，ADB 设备冲突有测试覆盖。
- 前端主页面、定时页、工具页复用 `LogPane`、`RunStopButton` 与 SSE patch 协议，产品体验已经统一。

### 3.2 当前真正的边界

当前结构更准确的描述是“**MAA 专用应用中有一套可复用运行内核**”，而不是“MAA 是通用框架的一个 integration”。证据包括：

- `process.run_streaming_process()` 接收 `MaaRuntime`，只为取得 cwd。
- `GenericRunManager`、`RunStateStore`、`Diagnostics` 都接收 `MaaRuntime`。
- `MaaRuntime` 同时包含框架目录和 MAA 专属 config/data/cache/state/bin 目录。
- `FrameworkSettingsManager` 反向依赖 `run_manager.state.RunTimeouts`。
- `run_resources.py` 同时包含通用资源对象和 MAA/ADB/default-device 逻辑。
- config API、schema validator、前端编辑器和动态选项都直接围绕 maa-cli task/profile 构建。

这不是当前功能的错误，但会使第二个 CLI integration 的接入成本接近复制一套 MAA 领域服务，而不是注册一个新 adapter。

## 4. 优先问题

### 部署前提：可信内网、单用户

**正式产品前提**

- 当前服务以 root 运行并监听所有网卡，属于方便测试的裸机方式，不是最终形态。
- 框架目标是可信内网中的单用户工具，不计划公网或多租户部署。
- API 无认证是该威胁模型下的有意简化，不应按公网控制面标准判为缺陷。
- API 可写配置、启动/停止任务、触发 maa-cli 自更新和资源更新、安装 APK、删除历史。
- README 给出 LAN 地址，符合预期使用方式。

**风险**

容器化的目标是隔离依赖和宿主资源，不是引入账号体系。剩余风险只需由既有内网边界承担：端口不得误发布到公网；容器不应获得 `privileged`、Docker socket、host network 或无关宿主目录。

**建议**

1. 容器内显式监听 `0.0.0.0`，Compose 只 publish 到预期 LAN 地址/端口；由路由器或宿主防火墙保证不进公网。
2. 当前不引入反向代理认证、用户数据库、session/token 或权限系统。
3. 容器不使用 `privileged`/Docker socket/host network；drop capabilities，使用 `no-new-privileges`。专用 UID 是低成本隔离措施，可保留但不扩展成权限技术栈。
4. TCP ADB 场景只需要普通网络；不要为方便连接 redroid 额外挂宿主设备。
5. 自定义脚本继续按可信本地管理员资源处理，重点防 path escape、参数拼接和意外宿主挂载，而不是增加用户授权模型。

### P0：维护更新可与活跃 MAA 运行并发

**现状**

`MaintenanceActionManager` 启动 core/resource/cli update 时未声明任何 resource；手动和定时 MAA 只声明 ADB device。不同 manager 可以并行，因此可以在 maa-cli/MaaCore 正运行时更新其二进制或资源。

**风险**

- 正在运行的进程读取到不一致资源。
- self-update 与新 run 启动竞争。
- 更新失败后留下部分运行时，影响后续所有任务。

**建议**

把资源模型扩展为 shared/exclusive claim：

- MAA run：共享读取 `runtime:maa`，独占对应 `adb-device`。
- MAA maintenance update：独占 `runtime:maa`。
- 未来其他 integration：声明自己的 runtime/config/device 资源。

不要用一个普通互斥 `maa-runtime` 锁替代，否则不同 ADB 设备上的 MAA run 也会被无必要串行化。

### P0：无换行输出会绕过超时与停止检查

**确认复现**

子进程写入 `partial`、flush、sleep 3 秒；设置 `runtime_kill_seconds=1`。实际耗时 3.01 秒，结果 `timed_out=False`、return code 0。

**根因**

`select()` 只说明 pipe 有字节可读，随后对 `TextIOWrapper.readline()` 的调用仍会等待换行或 EOF。在它阻塞期间，runtime/no-output/stop/force-stop/tick 逻辑都不会运行。

**建议**

- pipe 设为 non-blocking，使用 `os.read()`/selectors 读取 bytes，自行增量解码和按行切分。
- EOF 时 flush decoder 与 partial line。
- 增加“partial line + runtime kill”“partial line + force stop”“超长无换行输出”回归测试。

### 已修复：应用 lifespan 和优雅关闭

**现状**

- FastAPI lifespan 显式启动 scheduler，并在退出时调用统一 `WebServices.close()`。
- 关闭开始后 scheduler、四类 run manager 与 coordinator 同时进入 closing，拒绝新 run 并唤醒资源等待者。
- 活跃 run 先共享 60 秒正常停止窗口，剩余任务按进程组 SIGKILL，再共享等待 15 秒。
- 所有外部命令使用独立 POSIX session；stop/force-stop 作用于完整进程组。
- Uvicorn 信号入口先广播 shutdown，使 SSE 在 1 秒轮询内主动结束；5 秒 graceful timeout 只作兜底。
- scheduler/run thread 均在 lifespan 中 join，framework logging 最后 flush/close。

**验证**

- 四个 manager 同时活跃时能在共享 deadline 内停止并持久化。
- 忽略 SIGTERM 的 parent/child 进程组能被 force-stop 清理。
- 真实 SSE 长连接下，独立服务 SIGTERM 后约 1 秒退出，return code 0，无 cancellation traceback。
- systemd `TimeoutStopSec` 已调为 120 秒，与 Compose `stop_grace_period: 2m` 对齐。

### P1：同优先级资源冲突会无限阻塞请求线程

`RunCoordinator.acquire()` 对同优先级冲突一直等待，没有 deadline/cancellation。直接调用启动 API时，请求可能等待数分钟甚至更久，而不是立即返回冲突或显式进入队列；大量请求可能耗尽 FastAPI threadpool。

建议明确选择一种语义：

- 当前阶段：API 启动使用 non-blocking acquire，冲突返回 409 和 blocker 信息。
- 未来若需要排队：建立持久化 queue，启动 API 返回 `queued` run，而不是把 HTTP 连接当队列。

自动调度可以使用有 deadline 的等待/重试，但必须在等待期间继续响应 shutdown。

### P1：运行内存与历史文件没有闭环保留策略

**内存**

`GenericRunManager._runs` 和 `_plans` 从不移除完成项。plan 会持有 callbacks 和领域状态，run 会持有所有 retry 及日志块。常驻服务运行次数越多，内存只增不减。

**磁盘**

`RunStateStore` 会截断 recent run/retry 索引，但不会删除被淘汰 run 对应的 `history/framework/runs/**/*.json`。诊断文件有保留策略，结构化 history 没有。

**建议**

- manager 只保留 current + 少量 recent terminal snapshots；历史查询统一走 store。
- `_plans` 在 run 完成后立即释放。
- history retention 同时删除 index、history JSON、关联 artifacts/diagnostics，或明确采用按年龄/数量分层策略。
- 删除历史时校验并清理空目录和关联文件，返回完整删除结果。

### P1：崩溃恢复只恢复 run，不能恢复当前 retry 内容

retry 和结构化可见日志只在 retry seal 时写入 history。进程/主机崩溃时，最近 active retry 的结构化日志和 metadata 不在 durable history 中；启动恢复只把 run 标记 stopped。

对于“高可用自动化面板”，建议做节流 checkpoint：每 N 秒或 N 个 generation 将 open retry 快照原子写入；恢复时 seal 为 stopped/recovered。原始 diagnostics 可继续逐行 append，不需要重复设计。

### P1：APK 下载与安装缺少完整性/身份校验

当前 `download_file()` 只校验 HTTP 状态、Content-Type 和 Content-Length；安装后只检查 versionCode。增量 patch 和全量 APK 都没有 checksum、签名证书或 package identity 校验。

建议至少在安装前验证：

- APK package name 与预期一致。
- signing certificate digest 与已安装/配置的可信证书一致。
- 若上游 API提供 hash/size，校验 hash；manifest 记录来源、hash、证书、验证时间。
- 下载先写 `.part`，fsync/rename 后再进入 manifest。

## 5. 通用化与扩展性审计

### 5.1 先拆 `MaaRuntime`，不要先造插件系统

建议把当前运行时拆为：

```text
FrameworkPaths
  repo_root
  config_root
  state_root
  history_root
  debug_root
  cache_root

ProcessContext
  cwd
  base_env

MaaInstallation
  binary
  config_dir
  data_home
  cache_home
  state_home
  generated_config_dir
```

之后：

- `process` 只依赖 `ProcessContext`/cwd/env。
- `run_manager` 只依赖 store、diagnostics、coordinator 和 process executor protocol。
- `RunStateStore`、`Diagnostics` 只依赖 `FrameworkPaths`。
- MAA runner/maintenance/stage/infrast 才依赖 `MaaInstallation`。

这是接入其他 maa-cli 类工具的最低成本关键步骤。

### 5.2 建立 action/integration registry

不建议马上支持动态安装第三方 Python 包。先做内部显式 registry，即可解决硬编码扩展问题：

```text
IntegrationSpec
  id / title / version
  config providers
  actions[]
  resource resolver
  log profile factory
  optional frontend schema

ActionSpec
  id / title / description
  input schema
  build_start_plan(request, services) -> RunStartPlan
  history scope
  permissions/capabilities
```

MAA manual run、maintenance、game update 和自定义脚本都可以逐步成为 action。`GenericRunManager` 继续作为执行内核，不需要再造第二套 lifecycle。

### 5.3 自定义脚本接口的建议边界

当前脚本能力只有 schedule 的 `before_run`/`before_retry` hook，且固定 `/bin/sh <path>`。要变成正式接口，建议分两层：

1. **Script definition**：可信管理员在本地目录提供脚本与 manifest。
2. **Script action instance**：用户在 UI 选择脚本、填写 schema 定义的参数、选择 hook/独立运行方式。

manifest 至少应声明：

- id/title/description/interpreter 或 argv；不要接受拼接后的 raw shell command。
- input JSON Schema、默认值、secret 标记。
- cwd、允许继承的环境变量、输出编码。
- timeout/retry policy。
- resource claims（ADB、runtime、容器、网络等）。
- 可用于哪些 hook，退出码/结果解释规则。
- 日志 profile 与敏感值脱敏规则。

第一版只读取本地管理员管理的 manifest，不需要先做认证或用户权限。若以后增加 Web 编辑，也只写入专用脚本卷，并保持路径校验、结构化参数和无 raw shell 拼接。

### 5.4 固定类型仍散落在外层

虽然 `RunKind = str` 已放开，但以下位置仍封闭：

- history API 的 `kind` query 是四项 Literal。
- 前端导航和四套页面直接绑定四种 run domain。
- 工具字段虽有 `kind`，前端仍全部渲染成文本框。
- API request/response TypeScript 类型手写，无法自动发现新 action。
- config route 和 validator 只认识 maa-cli profiles/tasks。

registry 稳定后，应让 history filter、工具表单、导航/action 列表和 OpenAPI schema 从 descriptor 派生；不需要让整个 UI 动态插件化。

## 6. 后端模块整合与拆分建议

### 6.1 应拆分

#### `run_manager/manager.py`

保留单一 facade，但将内部实现拆为：

- `models.py`：start plan、callbacks、decision、completion、script specs。
- `lifecycle.py`：start/current/stop/finish/retention。
- `executor.py`：attempt loop、command execution、timeout/result mapping。
- `script_hooks.py`：hook 解析与执行。
- `events.py`：visible/diagnostic event 写入。

重点不是降低行数，而是让 process executor、persistence 和 callback orchestration 能分别测试。

#### `scheduler/service.py`

拆为：

- `engine.py`：后台 tick、due detection、trigger 去重、shutdown。
- `service.py`：CRUD/status/API facade。
- `maa_run.py`：`ScheduledMaaRunCallbacks` 与 plan 构建。

调度器不应直接承担 MAA attempt 细节。

#### `maa/log_templates.py`

按稳定规则族拆分为 task lifecycle、summary、recruit/infrast/fight、git/resource。公共注册函数仍留在 `log_templates/__init__.py`，避免调用方知道内部文件。

#### 前端大页面

- `SettingsPage` 拆成 framework/theme、profile、maa-cli update、maintenance 四个 feature panel + `useMaintenanceRun`。
- `SchedulePage` 拆成 `useScheduleDetail`、`useScheduleRun`、history controller 和 route shell。
- `MainPage` 抽出 task draft reducer/store 与通用 run stream hook。

### 6.2 应整合

- 四个页面重复的 `get current → EventSource → apply patch → error/reconnect` 应整合为 `useRunStream()`。
- 三处 retry count localStorage 读写应整合为 `useStoredBoundedNumber()`。
- manual/scheduled MAA 共用的 task descriptor、collector、generated config、MaaCore delta 和 retry task helper可收敛到 MAA domain 内部的 `MaaAttemptSession`，但最终策略仍由 manual/schedule callback 决定。
- `ToolCommand` 与 `CommandSpec` 重复；registry 建立时只保留 `CommandSpec`。
- `schedule_priority(trigger)` 和 `priority_name`/numeric metadata 存在双重表达，应统一为 policy 解析后的单一 claim 信息。

### 6.3 不建议整合

- 不要把结构化可见日志、raw external logs、framework logging 合并成一个存储类。
- 不要把 scheduler daily stats/trigger state 重新塞回通用 run store。
- 不要把 MAA 日志翻译规则下沉到通用 log pipeline。
- 不要让 `GenericRunManager` 理解 task id、MAA result 或 schedule policy。

## 7. 配置、API 与持久化

### 7.1 从宽松 dict 迁移为领域模型

大量 endpoint 和 manager 使用 `dict[str, Any]`，Pydantic 只验证最外层字段。建议优先为以下本项目自有配置建立 Pydantic 模型：

- framework settings。
- script/action manifest。
- tool/action input。
- schedule config 与 retry/timeout/resource claim。

maa-cli 原生配置仍可保持 schema-driven dict，避免重复维护完整上游模型。

### 7.2 设置保存不是跨文件事务

`PUT /api/settings` 依次写 framework、profile、cli 三个文件。虽然单文件是原子替换，但中途 I/O 失败会留下部分更新。可先将三个内容写到 staging，全部 fsync/validate 后按固定顺序 replace，并保留 rollback backup；或拆成三个独立 endpoint，明确部分成功语义。

### 7.3 schedule id 语义需收紧

PUT path 包含 `schedule_id`，payload 也含 `id`，实际写入使用 payload id。若两者不同，可能新建另一个文件而保留旧文件。建议：

- 普通 PUT 要求 path id 与 body id 相同。
- 重命名单独提供 endpoint，并原子移动文件与关联引用。

### 7.4 解析失败不应静默等价于空状态

`read_json_object()` 对 JSON decode error 返回 `{}`。原子写降低了损坏概率，但一旦文件损坏，下一次更新可能把原有状态当空状态覆盖。建议区分 missing 与 corrupt：损坏文件改名为 `.corrupt-<timestamp>`、记录高优先级诊断并拒绝破坏性覆盖。

## 8. 前端审计

### 8.1 当前优点

- TypeScript strict 已开启。
- URL 是任务配置/子任务选择的主要真相来源。
- 编辑采用 draft + explicit save，破坏性操作有确认。
- 日志组件能同时展示 live 与 history，并适配通用 metadata/artifacts。
- 响应式布局和共享基础组件已经形成。

### 8.2 主要问题

1. **没有自动化前端测试**：Playwright 是依赖但没有 test script/测试文件；JSON Forms managed param、drag/drop、dirty/reset、SSE reconnect 都只有人工保障。
2. **API 类型手写且只做类型断言**：`readJson<T>` 不做 runtime validation；后端 schema 变化可能静默进入错误状态。
3. **run stream 逻辑复制四次**：错误处理和恢复语义容易漂移。
4. **页面 state 过密**：Schedule/Main/Settings 同时承担加载、草稿、run stream、历史、业务事件和渲染。
5. **单 bundle 偏大**：768 kB minified，路由没有 lazy load；JSON Forms 等重依赖进入主包。
6. **插件扩展能力不足**：工具 field.kind 未实际驱动控件类型，任务 schema 也由静态文件表决定。

### 8.3 建议测试优先级

首批前端测试不必追求高覆盖率，应覆盖高风险状态机：

- `runStream` reset/patch/reconnect。
- MainPage 新建/修改/复位/保存/删除 draft。
- managed array + runtime metadata 同步。
- schedule task config 切换、dirty 禁止运行、history 切换。
- stopping → force-stop 按钮转换。

使用 Vitest/React Testing Library 做 reducer/hook/component，Playwright 只保留 3–5 条关键端到端流程。

## 9. 测试、CI、依赖与交付

### 9.1 后端测试缺口

当前 66 个测试对 run manager、coordinator、scheduler policy、日志规则覆盖较好，但缺少：

- 真实 HTTP CRUD/validation/auth（当前只检查 OpenAPI path 和一个 ASGI GET）。
- app lifespan、scheduler shutdown、服务停止时活跃 run 收尾。
- process partial-line、process tree、强停后代进程。
- manager 内存 eviction/history retention。
- maintenance 与 active run 的资源冲突。
- state JSON 损坏恢复、磁盘写失败、跨文件设置部分失败。
- 两个以上 integration/action 的契约测试。

### 9.2 CI

建议最小 CI：

```text
backend: uv sync --frozen --group dev
         ruff check
         python -m compileall
         python -m pytest
frontend: npm ci
          npm run typecheck
          npm test
          npm run build
security: npm audit --omit=dev
          pip-audit/OSV scan
repo: git diff --check（本地）/ lockfile consistency
```

为 `pytest`、typecheck、frontend test 建立正式 script，避免依赖开发者记住特殊命令。

### 9.3 Python 依赖公告

对当前环境执行 `pip-audit`，报告涉及：

- `idna 3.11`（fix 3.15）。
- `lxml 6.0.2`（fix 6.1.0）。
- `requests 2.32.5`（fix 2.33.0）。
- `soupsieve 2.8.1`（fix 2.8.4）。
- `urllib3 2.6.2`（fix 2.7.0；另有 2.6.3 修复项）。

实际暴露评估：项目没有使用 user-supplied CSS selectors、`requests.extract_zipped_paths()` 或 user-supplied IDNA 域名，因此其中多项是低可利用性；但 game updater 对上游返回 URL使用 streaming download 和 redirects，urllib3 的资源耗尽类公告更值得尽快处理。建议刷新 lock、升级到修复版本并重跑真实 game update smoke test。

### 9.4 可复现部署

Docker 化是既有目标，但应在 `FrameworkPaths` 与 `MaaInstallation` 拆分之后实施。至少提供：

- Dockerfile/Compose 或版本控制内的 systemd unit 二选一。
- 非 root 用户、持久卷路径、health/readiness endpoint。
- 版本固定的 maa-cli/MaaCore 安装流程与 checksum。
- backup/restore 文档（config/state/history，diagnostics 可选）。
- 升级前停止新 run、等待/停止当前 run、再替换 runtime 的流程。

## 10. 建议目标结构

```text
src/maa_auto_panel/
  app/
    runtime.py            # lifecycle / shutdown / service container
  api/
    routers/
    auth.py
    schemas/
  core/
    paths.py              # FrameworkPaths
    process.py            # non-blocking process executor
    actions.py            # IntegrationSpec / ActionSpec registry
    resources.py          # shared/exclusive claims
  run_manager/
    models.py
    lifecycle.py
    executor.py
    events.py
    store.py
    router.py
  logs/                   # only generic pipeline/state/records
  scheduler/
    engine.py
    service.py
    config.py
    state.py
  integrations/
    maa/
      installation.py
      actions.py
      manual_run.py
      scheduled_run.py
      maintenance.py
      config/
      logs/
    game_update/
      action.py
      downloader.py
      verifier.py
    scripts/
      manifest.py
      action.py
  storage/
  web/
frontend/src/
  features/
    runs/
    tasks/
    schedules/
    settings/
    tools/
```

这是一条演进方向，不建议一次性搬目录。先通过依赖倒置建立边界，再按变更频率移动文件。

## 11. 分阶段执行建议

### 阶段 A：运行与安全基线（最高优先级）

1. 修复 non-blocking process output 与 partial-line 测试。
2. 引入 app lifespan、scheduler shutdown、process group 停止。
3. 增加 maintenance exclusive runtime claim。
4. 启动冲突改为 non-blocking 409 或正式 queued state。
5. 完成可信内网容器边界：专用 UID、最小 capability、持久卷和仅 LAN 的显式端口发布；不增加认证技术栈。
6. 修复/重建 `.venv`，清理旧 `linux-maa` 安装元数据。

### 阶段 B：长期运行可靠性

1. manager 内存 eviction 与 plan 释放。
2. history/artifact 联动 retention。
3. open retry checkpoint 与 crash recovery。
4. state corruption 隔离与备份。
5. APK checksum/certificate/package 验证。

### 阶段 C：框架边界

1. `FrameworkPaths` / `ProcessContext` / `MaaInstallation` 拆分。
2. 通用层移除 `maa.*` 依赖。
3. shared/exclusive resource policy。
4. Pydantic framework/action/schedule models。

### 阶段 D：扩展接口

1. 内部 Integration/Action registry。
2. game update 与 maintenance 迁为 action。
3. 自定义 script manifest + 独立运行 action。
4. history filter、工具 form 与 UI导航消费 descriptors。
5. 用一个第二 CLI fake integration 做契约测试，验证扩展不是只对 MAA 成立。

### 阶段 E：前端与交付

1. `useRunStream`、draft reducer、页面拆分。
2. OpenAPI 类型生成或 response runtime validation。
3. Vitest + 少量 Playwright E2E。
4. route lazy loading/manual chunks。
5. CI、Docker/systemd artifact、backup/restore/upgrade 文档。

## 12. 最终判断

当前项目的核心功能和近期 run-manager 重构方向是正确的，可以继续演进，无需推倒重来。下一步最有价值的工作不是继续扩大 `GenericRunManager`，也不是马上做动态插件，而是：

1. 把进程停止、应用关闭、资源更新互斥和网络安全做成可信基础。
2. 把 framework path/process/store 从 `MaaRuntime` 中抽出来。
3. 在此基础上用内部 action registry 落地自定义脚本和第二 integration。

完成这三点后，项目才会从“功能完整的 MAA 面板”真正跨到“可安全扩展的自动化运行框架”。
