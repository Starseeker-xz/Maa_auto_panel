# Session 2026-07-11_1805-consolidate-audits

## 目标

将根目录三份审计性质文档整理为前端、后端两份，并固定后续维护规则。

## 完成内容

- 删除 `PROJECT_AUDIT.md`、`PATH_MANAGEMENT_AUDIT.md`、`CONTAINERIZATION_PLAN.md`。
- 新增 `BACKEND_AUDIT.md`，合并后端架构、运行时、路径、持久化、容器和交付边界。
- 新增 `FRONTEND_AUDIT.md`，整理前端状态、测试、bundle、页面职责与类型边界。
- 两份报告均明确：后续审计只修改对应报告；改代码时报告仅作可能过时的参考，必须先核对当前实现。
- 更新 README 的容器边界引用及项目持久状态。

## 取舍

- 没有原样拼接三份旧报告。旧报告包含大量已完成步骤、重复建议、旧代码规模、旧目录容量和一次性 Docker 示例；保留它们会继续制造过时权威感。
- 保留仍有决策价值的活跃风险、架构边界、来源会话与重新验证要求。

## 验证

- `rg` 检查旧文件引用；README 中唯一有效旧引用已改为 `BACKEND_AUDIT.md`。
- `git diff --check` 通过。
- 仅修改文档与状态记录，未运行代码测试。

## 后续：优化 runtime 资源模型

- 审计确认 `RunResource` 原先只有 kind/identifier，相同资源一律互斥；MAA run 只声明 ADB，maintenance 没有 claim。
- 为 `RunResource` 增加 `shared`/`exclusive` access，默认 exclusive 以保持设备等现有资源语义。
- 同 kind/identifier 的 claim 仅在至少一方 exclusive 时冲突。
- 新增 `maa_runtime_resource()` 与 `maa_run_resources_from_profile()`；手动、定时 MAA 统一声明共享 runtime + 独占 ADB。
- core/resource/cli maintenance update 声明独占 MAA runtime。
- `RunLease`/`RunStartPlan` 新增 `preemptible`；maintenance 为 false，防止高优先级 schedule 抢占并中途停止 runtime 更新。更高优先级请求遇到不可抢占 lease 时返回 `RunConflictError`。
- 工具 `game-update` 不读取 MAA runtime，本轮维持仅独占 ADB，避免扩大无依据的锁范围。
- 定向测试 20 passed；最终 `compileall` 通过；完整 pytest 86 passed；`git diff --check` 通过。

## 后续：明确资源冲突请求语义

- 审计确认路由虽捕获 `RuntimeError` 并映射 409，但 `RunCoordinator.acquire()` 会先等待，因此交互式 HTTP 请求仍可能无限占用 worker。
- `RunCoordinator.acquire()` 新增显式 `wait` 参数；`RunStartPlan.wait_for_resources` 默认 false，`GenericRunManager` 据此 non-blocking acquire。
- 手动 MAA、手动 schedule、tool、maintenance 遇到资源冲突立即抛出 `RunConflictError`。
- 只有 scheduler 自动触发设置 `wait_for_resources=True`，保留后台等待/优先级抢占与 shutdown 唤醒行为。
- Web 统一将 `RunConflictError` 映射为结构化 HTTP 409，detail 含 `code=run_resource_conflict`、requested lease 与 blockers。
- 定向测试 33 passed；最终 `compileall` 通过；完整 pytest 87 passed；`git diff --check` 通过。

### 回退

用户澄清预期是保留既有优先级行为：低优先级手动请求遇到高优先级占用立即失败并展示原因；并非所有交互式冲突都 non-blocking。上述 `wait_for_resources`、结构化 409 和路由特判已完整回退，shared/exclusive runtime 资源模型与 maintenance 不可抢占仍保留。

原 P1 的准确范围是同优先级冲突：同步 HTTP start 会等待 active lease 释放，期间占用 worker，且没有 queued run id/状态。该问题暂不修改，等待明确同优先级产品语义。

## 后续：资源申请成为完整运行阶段

- 用户明确最终语义：manager 先建立持久化、日志管线和 SSE，再在 worker 内经过运行前操作后申请资源。
- `GenericRunManager.start()` 不再同步 acquire；先创建/持久化 run 并启动 worker，调用方立即获得可观察状态。
- 第一次 attempt 执行 on_start/before_run 后申请资源；资源失败写入原日志管线，封存 failed retry/run，不构建或启动 command，不进入后续 retry。
- 同优先级等待写 warning event；`metadata.resource_wait` 实时持久化 waiting/blockers，取得后更新 acquired 并写 event。
- `RunCoordinator.acquire()` 支持 wait observer、全局 deadline 与 run-local cancel；manager stop 会主动唤醒等待者。
- framework 设置新增 `framework.run_resources.wait_timeout_seconds`，默认 300，范围 1..86400 秒；四类 manager 动态读取同一设置。Settings UI 新增全局输入项。
- 资源等待超时形成完整 failed run；等待中 stop 形成 stopped run；二者均不启动实际 command。
- 测试断言最初误按扁平 `entry.text` 读取结构化日志，且断言失败后未释放测试 blocker，导致非 daemon 等待线程挂住 pytest；改为读取 title/messages 并用 finally 清理 lease。
- 完整验证：compileall 通过，pytest 90 passed，前端 production build 通过，`git diff --check` 通过。bundle 仍有既存 >500 kB warning（771.98 kB）。
- 验证命令曾错误地在 `frontend/` cwd 执行根目录 `.venv/bin/python`，立即失败且无环境影响；随后从仓库根正确重跑。

## 后续：通知栈与在线 Toast 分离

- 根因：后端把 toast policy 同时当作是否缓存事件；SSE 新连接无差别重放缓存；前端只有最多 4 个 Toast，没有通知历史。
- 所有通知现在都会进入后端 100 条有界事件栈并递增 sequence；toast 只控制弹窗渠道。
- SSE 在连接开始时捕获 sequence ceiling，逐条附加 `delivery.replayed`，区分 backlog 与连接后的 live event。
- tag spec 新增 important/replay_toast；事件会携带 toast、important、replay_toast。error/warning/非 success 默认允许上线补弹；成功不补弹；更新可用和 runtime 缺失可显式补弹。
- 前端右上角铃铛打开右侧 overlay panel，显示最近 100 条通知；重要未读按 localStorage last-read sequence 显示红点，打开面板后标记当前通知已读。
- Toast 移到右上角铃铛下方。在线新事件按 toast policy 弹出；replay 仅在 replay_toast 为 true 时弹出，其余静默进栈。
- 通知定向测试 6 passed。用户随后澄清离线失败也必须补弹，最终规则调整为仅 success 默认不补弹；最终完整回归 pytest 92 passed，compileall、前端 production build 与 `git diff --check` 通过。bundle 仍有既存 >500 kB warning（775.53 kB）。

## 后续：设置拆页、主题前端化与更新刷新

- 设置路由拆为 `/settings` 基础设置（设备配置 + 更新）、`/settings/framework`（框架 + 通知）、`/settings/theme`（主题）。三页共享顶部分类导航。
- 主题页独立为 `ThemeSettingsPage`，只读写 localStorage 并立即应用；App 启动不再请求后端设置决定主题。后端默认设置删除 theme，并在 merge/write 时移除遗留 key。
- maintenance 运行从 running/stopping 进入终态后自动调用 update-info；本页发起的极快运行也通过 ref 标记触发刷新。
- 现场 run `0ff39d6eb688`（20:02:48–20:03:55）raw stdout 仅 `Already up to date.`，stderr 仅 MaaResource fetch，无 Core 安装文本。直接裸跑 binary 曾误报 MaaCore 不可读；使用 `scripts/maa-env maa version` 正确确认 maa-cli v0.7.5 / MaaCore v6.14.1，用户确认 smoke 任务可运行，故撤回 Core 损坏判断。
- 日志“结束时一次出现”的高可信前端竞态：start POST response 与 maintenance SSE 并发，较晚返回的较旧 POST snapshot 可覆盖已由 SSE 写入的 command event；之后上游约 67 秒无新行，最终 patch 才把完整 retry 恢复。另有已知 readline/上游缓冲风险。本轮按用户要求只诊断，不修改。
- 首轮拆页验证：frontend production build 通过，相关后端 31 passed。最终完整回归 compileall、pytest 92 passed、frontend production build 与 `git diff --check` 均通过；bundle 保留既存 >500 kB warning（778.28 kB）。

## 后续：紧凑设置导航与通知抽屉修正

- 设置分类导航改为 `w-fit` segmented control，不再占满内容宽度。
- 通知抽屉标题简化为“通知”，删除说明副标题；宽度由 28rem 缩为 18rem。
- 通知条目抽为 `NotificationItem`；删除按钮默认弱化，仅 hover/focus 时强调。抽屉右下角新增“清空通知”。
- 逐条删除/清空使用浏览器 localStorage deleted event ids，SSE 重连/页面刷新不会重新显示；不删除后端共享有界事件缓存。
- 未读从 sequence 改为 event id 集合，避免后端重启 sequence 归零导致新通知永远不未读。所有未读都有提示，重要未读使用红点；打开抽屉标记当前事件已读。
- smoke 在线不 Toast/离线成功无未读的直接原因是 systemd 后端从 03:06 未重启，旧事件无 `delivery/important/replay_toast`，新版前端在入栈后读取字段失败并 catch。不是通知 listener 未发布。
- 确认 manual/schedule/maintenance 均为终态、tool idle 后重启 `maa-auto-panel-webui.service`。新 PID 9847，启动时间 20:25:26 UTC；新版首页 bundle 与通知 settings API 字段验证通过，服务保持 active。
- 最终验证：compileall 通过，pytest 92 passed，frontend production build 与 `git diff --check` 通过；bundle 既存 warning 779.47 kB。

## 后续：App Toolbar 与 shadcn 通用组件迁移

- 右上角改为融入 viewport 的 App Toolbar，仅左边框/下边框和左下圆角；三个按钮为 Scrcpy（disabled 预留）、设备截图（disabled 预留）、通知。
- Toolbar z-40；通知 Sheet 使用 Radix portal z-50，Sonner 使用自身顶层 portal，均覆盖 Toolbar。
- 通知抽屉从 18rem 扩到 22.5rem。真实 1440x900 Playwright 截图检查 Toolbar、segmented 和打开 Sheet，视觉与层级符合要求；截图仅存 `/tmp`。
- 手写 Toast DOM、计时与动画完整删除，安装 `sonner` 并新增 shadcn 风格 `ui/sonner.tsx`；Toast 队列、动画、关闭与 aria 由 Sonner 管理。
- 通过 `npx shadcn@latest add sheet -y` 引入官方 `ui/sheet.tsx` 与 `radix-ui` 依赖；手写 drawer overlay/portal/focus/动画删除。
- 新增共享 `SegmentedControl`，统一设置三页、定时页设置/统计、任务编辑常规/高级。
- 新增共享 `FocusDeleteButton`，支持普通/floating 模式；通知条目使用 floating，不占文本布局空间，并迁移任务子项、定时时间点、统计历史和数组编辑器的重复 delete 样式。
- 项目级规则已写入 project lessons，前端审计新增 P1：系统性检查 shadcn/Radix/Sonner 通用组件复用。
- 环境效果：frontend 新增 production dependencies `sonner`、`radix-ui`，package.json/lock 已更新；npm audit 0。
- 最终验证：compileall 通过，pytest 92 passed，frontend production build、npm audit、`git diff --check` 通过，systemd active。引入 Sheet/Sonner 后 bundle 为 820.35 kB（gzip 258.03 kB），既存 >500 kB warning 更明显，应在后续 lazy-loading 审计处理。

## 提交前简单审计

- 用户要求简单审计并提交当前连续工作。
- 范围确认：三份旧根目录报告由前后端两份替代；资源生命周期/共享独占模型、通知系统、设置拆页、主题前端化、通用前端组件与状态记录属于同一工作集，无无关大文件。
- 资源 lease 的成功、冲突、超时、取消、异常终态释放路径已核对；等待状态持久化和通知 listener 异常隔离保持明确。
- 通知后端缓存 100 条，前端 recent 100 条，read/deleted ids 持久化截断 500；SSE replay/live 及 toast-disabled 入栈有测试。
- 前端基础交互优先复用 Sonner/shadcn Sheet/Radix；依赖 lock 完整，npm audit 0。
- 扫描未发现 console.log/debugger/TODO/FIXME 或仓库内临时截图。旧审计文件名仅在新报告来源说明出现。
- 非阻断已知项：`process.py` readline/partial output 风险仍活跃；frontend bundle 820.35 kB warning 已记入审计。
- 提交前基线：compileall passed；pytest 92 passed；frontend production build passed；npm audit 0；`git diff --check` passed；systemd active。
