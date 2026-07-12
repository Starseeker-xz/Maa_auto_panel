# Maa Auto Panel 前端审计

状态：持续维护，结论可能随代码演进过时

最近整理：2026-07-11

整理会话：`2026-07-11_1805-consolidate-audits`

## 使用规则

- 后续前端审计只修改本文件。
- 修改前端代码时可参考本文件定位风险，但必须先阅读当前组件、hooks、类型和相似实现；审计结论很可能已经过时。
- 审计应更新或删除失效结论，不累计旧 bundle 数字、旧文件行数和已完成待办。
- 后端、运行时、路径、容器与交付问题维护在 `BACKEND_AUDIT.md`。

## 当前判断

前端已经形成一致的运行体验：主页面、定时任务、工具和维护流程复用日志展示、停止按钮与 SSE patch 模型；全局通知使用独立事件流和统一 Toast。当前重点不是重写，而是继续收紧页面职责、补高风险状态测试并控制 bundle 边界。

## 值得保留的边界

- `LogPane`、`RunStopButton` 等跨运行类型组件继续复用。
- 服务端保持 run/retry 的权威状态，前端只做展示所需派生。
- SSE patch 应按 generation/identity 合并，不以本地列表长度充当 cursor。
- 通知中心保持在 App 根部，通知设置面板与事件展示解耦。
- Toast 只承担在线即时提醒与少量上线补弹；近期通知由右侧抽屉承载，不能再用 Toast 数量上限充当历史保留。
- Settings 页面作为编排层，具体设置块逐步收敛到明确 panel 组件。
- 设置现分为基础设置（设备与更新）、框架设置（运行策略与通知）和独立主题页；主题只保存在浏览器 localStorage，不再与后端 framework settings 双向同步。
- 三类设置使用内容宽度的紧凑 segmented navigation，不再让分类切换控件占满页面。

## 活跃问题

### 已解决：通用组件复用边界

`2026-07-12` 已按基础设施语义完成收敛：手写 `ConfirmDialog` 保留领域 API，但内部改用 Radix/shadcn AlertDialog，获得 Portal、modal focus trap、Escape、焦点恢复和背景隔离；busy 时禁止关闭。设置分类不再伪装 tab，改为真实 `NavLink` navigation；配置编辑器与定时详情改用 Radix Tabs，具备 roving tabindex、方向键与 tabpanel 关联，旧 `SegmentedControl` 已删除。

任务子项、定时时间点与 primitive array 的 inline rename 生命周期统一到无 UI 的 `useInlineRename`，共享 Enter/blur 提交、Escape 取消及 blur 防重复提交；领域列表仍各自拥有选择、字段、删除与排序，避免形成覆盖所有领域的巨型 row component。任务与 array 的原生拖拽仍缺完整键盘排序；若后续补可访问排序，应集中选择成熟 sortable primitive，再统一迁移，不能继续堆按键分支。

App Toolbar 的原生 `title` 已改为 Tooltip + `aria-label`，包括 disabled 预留按钮。`FormFields`、`ScrollArea`、LogPane 原生 overflow、Sonner、Sheet、Select 和 Checkbox 等现有边界继续保留，不增加无领域价值的 wrapper。侧栏 schedule 子项和 Tool list 虽仍有领域内按钮样式，但数量少且行为不同，目前不值得抽象。

### P1：缺少自动化测试

旧审计未发现前端自动测试。实施前先核对当前测试配置；若仍为空，优先覆盖高风险逻辑，而不是先追求页面截图数量：

1. SSE reconnect、generation patch、run/retry identity 切换。
2. task editor 中 params 与 framework-managed metadata 的合并更新。
3. schedule 表单、动态选项和停止/完成状态转换。
4. NotificationCenter 的去重、持续条件恢复和断线重连。

EventSource 页面测试不要等待 `networkidle`；使用 `domcontentloaded` 和目标 DOM/状态断言。

### 已解决：页面与编辑器 bundle 分块

`2026-07-12` 已建立两级动态边界：Main、Schedule、Tools、Settings、Theme 五类页面由 `App` 按 route lazy load，App shell、Sidebar、NotificationCenter 和主题初始化留在入口；Main 仅在选中 task item 时 lazy load `ConfigEditorPane`，因此 JSON Forms、vanilla renderers、PrimitiveArrayEditor 和七份 schema 不再进入普通 Main/Settings/Tools 首屏。共享 `LazyBoundary` 提供稳定尺寸 fallback、按 route/item reset 和 chunk 失败后整页重试，不会让整个 App 白屏。

实施前单 JS 为 830.30 kB（gzip 260.46 kB）；实施后入口为 413.34 kB（gzip 131.93 kB），ConfigEditorPane 为 289.90 kB（gzip 94.30 kB），各 route chunk 为 1.58–27.37 kB。当前最大 chunk 均低于 Vite 500 kB warning，不配置脆弱的 manualChunks。七份 schema 继续留在 editor chunk：现有 editor 已形成清晰隔离，再按 task type lazy 只会增加异步竞态和缓存状态，缺乏足够收益证据。

### P1：页面组件职责可能继续膨胀

历史上 `SettingsPage`、`SchedulePage` 和 `MainPage` 较大。拆分应沿业务边界进行：页面负责查询与编排，panel/form 负责局部交互，纯转换进入独立函数，服务端状态同步进入 hooks。不要仅按行数制造大量薄 wrapper。

`2026-07-11` 已先将主题拆为独立 `ThemeSettingsPage`，基础/框架设置通过子路由分开展示；`SettingsPage` 仍同时编排基础与框架的数据获取/保存及 maintenance stream，后续若继续增长，可按这两个领域拆成各自页面 hook，而不是重新合并。

### P2：固定运行类型散落

前端筛选、标签、路由和状态展示若硬编码 manual/schedule/tool/maintenance，会阻碍后端 action/integration registry。后端模型稳定后，前端应消费 action descriptor 或集中映射；在此之前避免新增更多分散 switch。

### P2：类型与展示转换边界

API wire types、表单模型和展示模型应分开。日期、状态标签、metadata/artifact 映射和动态选项转换集中处理，避免页面内重复解析宽松 dict。删除 schema 字段时同步模板 general/advanced keys 与 JSON Forms 控件。

### 已解决：离线通知重放挤占 Toast

`2026-07-11` 已将通知历史与 Toast 分离：所有 SSE 通知进入 shadcn Sheet；在线通知由 Sonner Toast，离线成功只入栈，离线失败/警告上线补弹。右上角 App Toolbar 统一承载 Scrcpy（预留）、设备截图（预留）和通知；Sheet/Sonner 层级覆盖 Toolbar。抽屉宽 22.5rem，通知条目支持悬浮 focus-delete 和右下角清空；已读/删除按 event id 保存在当前浏览器。

## 审计时的验证基线

不要复用旧报告中的 bundle 大小或文件规模。按改动范围重新检查：

- TypeScript 类型检查与 production build。
- 相关 unit/component tests；涉及 SSE 时增加 reconnect 与乱序 patch 场景。
- `npm audit` 仅作为依赖检查之一，不替代运行行为验证。
- 关键页面手工 smoke：加载、断线重连、启动/停止、历史切换、设置保存和通知展示。
- `git diff --check`。

## 来源与整理说明

本文件由原 `PROJECT_AUDIT.md` 的前端审计部分整理而来，主要来源会话为 `2026-07-10_0416-full-project-audit`，并吸收了后续 Settings panels 与通知中心的现状。整理时删除了旧文件行数、旧 bundle 快照和已完成的页面拆分细节。
