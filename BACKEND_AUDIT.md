# Maa Auto Panel 后端审计

状态：持续维护，结论可能随代码演进过时

最近整理：2026-07-11

整理会话：`2026-07-11_1805-consolidate-audits`

## 使用规则

- 后续后端、运行时、持久化、路径、容器与交付审计只修改本文件。
- 修改代码时可参考本文件定位风险，但必须先核对当前实现；审计结论不是事实来源，也不是待办清单的强制优先级。
- 审计应更新结论状态，及时删除已失效的现场数据、代码行数和一次性实施步骤。
- 前端专属问题维护在 `FRONTEND_AUDIT.md`；跨前后端问题放在主要责任边界一侧，并在另一份报告中简短引用。

## 当前架构判断

项目已有一套可复用运行内核，但整体仍更接近“MAA 专用应用”，尚未完全成为 integration 驱动的通用框架。应保留以下基础：

- `GenericRunManager` 统一运行、重试、停止、日志、持久化和资源协调，领域差异由 callbacks 提供。
- live/history 使用统一的 `{run, retries}` 结构。
- 运行状态、结构化历史、诊断日志与 framework logging 保持分离。
- scheduler、四类 manager、coordinator 和 SSE 已纳入应用 lifespan 与共享关闭期限。
- 框架 data、integration runtime、download cache、ADB credential 已形成独立持久化边界。
- 通知事件缓存与 Toast 渠道已分离；SSE 明确标记 backlog replay/live，所有事件进入近期栈，Toast 与上线补弹由事件策略独立决定。

项目仍处于早期阶段。新增能力时优先收紧职责和删除重复路径，不为未发布的旧布局或旧 API 保留兼容层。

## 活跃问题

### 已解决：runtime 使用共享/独占资源边界

`2026-07-11` 已在 `RunResource` 中加入 `shared`/`exclusive` access，并统一采用以下模型：

- MAA run：共享 `runtime:maa`，独占对应 ADB device。
- MAA update：独占 `runtime:maa`。
- 未来 integration 声明自己的 runtime、config 和 device claims。

冲突只在 kind、identifier 相同且至少一方为 exclusive 时成立，因此不同设备上的 MAA run 不会因共享 runtime 被串行化。手动与定时运行通过同一 helper 组装 claims，maintenance 的 core/resource/cli update 均声明独占 runtime，并标记为不可抢占，避免高优先级 schedule 中途停止更新。协调器、manager、shutdown 相关测试通过。

### P0：流读取可能被无换行输出阻塞

历史复现显示，`select()` 后调用文本 `readline()` 仍可能等待换行或 EOF，使 timeout、stop、force-stop 和 tick 检查失效。健康实现应使用 non-blocking byte read、增量解码和自行分行，并覆盖 partial line、超长无换行输出及强停测试。实施前须确认进程执行器是否已改造。

2026-07-11 的 Core 更新现场再次观察到约 67 秒内没有进程输出，结束前仅收到 MaaResource git fetch；raw stdout/stderr 没有 Core 安装文本，但正确 runtime 环境确认 MaaCore 已从 6.14.0 更新到 6.14.1，用户 smoke 任务可运行。因此“无 Core 可见日志”不等于更新失败，仍需在修复 byte reader 时区分上游 batch 静默/缓冲与本地读取阻塞。

### 已解决：资源申请纳入完整运行生命周期

`2026-07-11` 已将资源申请从同步 `start()` 门禁移动到 `GenericRunManager` worker：

- `start()` 先创建 live state、持久化 run、接通 SSE/日志并返回；HTTP worker 不再等待资源。
- worker 创建第一次 attempt 容器并执行 `on_start`/`before_run` 后才申请资源，取得资源后才构建和启动实际 command。
- 低优先级申请被拒绝时，在既有日志管线写 danger event，将该 attempt 与整个 run 直接封为 failed；不执行 command，也不进入后续 retry。
- 同优先级冲突显示 waiting event；等待阶段通过 SSE/live state 可见，并将 blocker 与阶段实时写入持久化 run metadata。取得资源后写 acquired event 再继续。
- 全局 `framework.run_resources.wait_timeout_seconds` 控制所有运行的资源等待上限，默认 300 秒；超时形成完整 failed run，不单独为各运行配置。
- 等待中的 stop 会唤醒 coordinator，完整结束为 stopped；shutdown 仍会唤醒全部等待者。

当前 retry 仍兼作 attempt 生命周期与可见日志容器，因此资源冲突会留下一个 failed retry 记录，但其中没有实际 command/process 执行。这避免新增第二套 run-level 日志和 SSE 协议。

### P1：运行内存与历史保留策略未闭环

需核对完成 run 后 `_plans`、callbacks 和内存快照是否释放，以及 recent index 淘汰时是否同步处理 history、artifacts 与 diagnostics。保留策略必须同时约束内存和磁盘，不得只有索引上限。

### P1：active retry 的崩溃恢复粒度不足

若 open retry 只在 seal 时持久化，进程崩溃会丢失最近的结构化日志与 metadata。可采用按时间或 generation 节流的原子 checkpoint；恢复时将快照 seal 为 stopped/recovered。先核对现有 store 是否已实现等价机制。

### P1：APK 完整性和身份验证不足

下载与安装链路应核对 package name、signing certificate、上游 hash/size，并使用 `.part`、fsync、atomic rename。manifest 应记录来源、hash、证书和验证时间，不能只依赖 HTTP 状态、Content-Length 或 versionCode。

### P1：通用层仍可能依赖 MAA aggregate

路径所有权已拆为 `ApplicationPaths`、`FrameworkPaths`、`CachePaths` 和 `MaaInstallation`，但调用方类型依赖仍需逐步收窄：

- process 只依赖 cwd/env 或 `ProcessContext`。
- store/diagnostics 只依赖 `FrameworkPaths`。
- MAA runner、maintenance 和领域服务才依赖 `MaaInstallation`。

不要为了形式立即引入动态插件系统。先用内部 `ActionSpec`/`IntegrationSpec` registry 验证第二个 integration。

### P2：持久路径应表达逻辑根而非部署位置

历史、diagnostics、trash、artifact 和 download manifest 不应保存宿主绝对路径或依赖 repo root 的字符串。优先保存 `{root, path}` 或明确的 root-relative reference，由单一 resolver 做路径逃逸校验。修改相关代码前应抽样现有数据，避免只改新写入而破坏旧读取；项目未发布时只需对本机数据做一次性调整，不增加通用迁移框架。

### P2：解析失败不应静默等价为空状态

JSON/TOML 状态解析失败时应隔离损坏文件、写入诊断并阻止破坏性覆盖。所有 store 修改都应核对 atomic write、并发边界和失败恢复。

## 路径与持久化边界

当前目标布局：

```text
data/
  config/framework/
  config/maa/
  state/framework/
  history/framework/
  debug/framework/
runtime/
  maa/
cache/
  downloads/
ADB credential: 独立 /home/panel/.android volume
```

所有权规则：

- `data_root`：框架拥有的 config、state、history、debug。
- `runtime_root`：integration 安装、resource 与其 XDG 状态。
- `cache_root`：可重新下载的数据。
- ADB state：独立凭据边界，不扩展成持久化整个 HOME。
- 前端产物、schemas、默认模板和应用代码属于只读应用资产。

路径只在 composition root 构造一次。优先级保持“显式参数 > 环境变量 > 开发默认目录”，从任意 cwd 启动都不应改变数据位置。

## 容器与部署边界

容器文件用于固化部署边界，不代表默认切换生产。未经用户明确要求，不执行 build/up。当前约束：

- 单 panel 容器、外部 TCP redroid、普通 bridge 网络、单实例。
- 不使用 privileged、host network、Docker socket 或无关宿主目录。
- systemd/dev 与 Compose 实例不得同时连接同一设备或共享 data/cache/ADB state。
- `/app/data`、`/app/runtime`、`/app/cache/downloads` 和 `/home/panel/.android` 独立挂载。
- 应用镜像与可在线更新的 MAA runtime 独立演进。
- Dockerfile 与 runtime 使用固定 UID/GID；drop capabilities，启用 `no-new-privileges`。
- `tini` 与 Compose `init` 二选一。
- health 只表示进程存活；ready 才检查路径、runtime 和 scheduler 初始化。
- 关闭预算继续覆盖 SSE、scheduler、manager、进程组、持久化与日志 flush。

已知容器验收风险：官方 stable 安装可能产生 OpenCV SONAME 不一致的混合 runtime；`maa version` 不会加载所有设备插件，不能替代真实 redroid 任务 smoke test。禁止用伪造 SONAME symlink 掩盖依赖问题。

## 扩展方向

建议顺序：

1. 修正进程读取、runtime 资源互斥和长期 retention。
2. 收窄通用层对路径与 MAA aggregate 的依赖。
3. 建立内部 action/integration registry。
4. 用第二个 integration 验证边界。
5. 再设计可信本地 manifest 驱动的自定义脚本接口。

当前不需要数据库、微服务、动态第三方 Python 插件、用户系统或 RBAC。产品威胁模型仍是可信内网、单用户；若该前提改变，重新独立审计认证与授权。

## 审计时的验证基线

不要沿用旧报告中的测试数量、bundle 大小、目录容量或服务状态。每次相关审计按改动范围重新执行并记录当次结果，通常包括：

- Python lint/compile/test 与 `git diff --check`。
- 进程 partial-output、timeout、stop、force-stop 和 shutdown 测试。
- retention、corrupt state、路径逃逸和跨 cwd 测试。
- 容器仅在用户明确授权时构筑；构筑后验证最终镜像 import/CLI、空隔离卷启动、SIGTERM，以及条件允许时的真实设备任务。

## 来源与整理说明

本文件由原 `PROJECT_AUDIT.md` 的后端部分、`PATH_MANAGEMENT_AUDIT.md` 和 `CONTAINERIZATION_PLAN.md` 整理而来。原报告主要来源会话：

- `2026-07-10_0416-full-project-audit`
- `2026-07-10_1752-audit-data-paths`
- `2026-07-11_0111-audit-container-plan`
- `2026-07-10_2207-graceful-shutdown`

整理时删除了已完成的逐步实施清单、旧代码规模、旧现场容量和重复的 Dockerfile/Compose 示例；实际配置以仓库当前文件为准。
