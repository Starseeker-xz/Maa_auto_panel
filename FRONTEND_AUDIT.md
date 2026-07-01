# 前端完整审计报告

Session: `2026-06-30_2342-full-project-audit`

## 结论

前端当前已经具备上线可用的基本质量：路由完整，API 层集中，主要页面可构建通过，任务编辑、定时执行、设置与维护功能都已经形成闭环。

本轮审计确认的主要问题不是单点崩溃，而是典型 AI 生成项目后期会出现的结构性重复：

- 表单字段、帮助提示、插入线等小组件在多个文件重复实现。
- `SchedulePage` 同时承担路由、数据读取、草稿状态、左侧列表、设置面板、统计面板、运行控制，文件过大。
- 多个页面各自手写轮询清理逻辑。
- 定时配置切换绑定任务配置后，左侧子任务清单仍读取旧 `detail.task_config`，保存/重载前 UI 会显示旧配置。
- API 错误格式化过于粗糙，FastAPI 默认 422 或项目自定义 validation errors 容易变成不可读 JSON。

已完成修正：公共字段组件、tooltip、插入线、轮询 hook 已提取；`SchedulePage` 已拆出定时左侧面板和设置/统计面板；定时配置切换任务配置的 UI 同步 bug 已修；API 错误格式化已补强；构建验证通过。

## 前端结构

### 入口与路由

- `frontend/src/main.tsx`
  - 挂载 React 根节点。
  - 引入全局 CSS。

- `frontend/src/App.tsx`
  - 提供 `TooltipProvider` 与 `SidebarProvider`。
  - 根据路径识别当前页面：主界面、定时执行、小工具、设置。
  - 启动时读取后端设置或浏览器本地主题并应用主题。
  - 监听系统深浅色变化。
  - 每次路径变化时刷新侧边栏定时配置列表。
  - 路由：
    - `/`
    - `/tasks/:taskConfig`
    - `/tasks/:taskConfig/items/:taskItemId`
    - `/schedule`
    - `/schedule/:scheduleId`
    - `/tools`
    - `/settings`

观察：

- `App.tsx` 的职责基本合理，但侧边栏 schedule 列表刷新仍与 shell 状态耦合。当前规模可接受。
- 旧版 `Page` 类型缺少 `tools`，已补齐为 `"main" | "schedule" | "tools" | "settings"`。

### API 层

- `frontend/src/lib/api.ts`
  - 所有页面 API 请求统一从这里发出。
  - `readJson()` 负责 fetch、JSON 解析、HTTP 错误抛出。
  - API 覆盖：
    - 配置列表、读取、保存、删除。
    - 手动运行启动/停止/查询。
    - 定时配置列表、读取、保存、删除、运行、停止。
    - 设置读取/保存。
    - 维护动作和版本信息。
    - MAA stage 和基建排班选项。

发现问题：

- 之前 `formatErrorDetail()` 只处理字符串和 `{ message }`，FastAPI 默认 422 数组或项目 validation errors 会直接 JSON.stringify。

修正：

- 已增加数组型错误、`loc/msg` 错误、`validation.errors` 错误的可读格式化。

### 公共类型与工具

- `frontend/src/lib/types.ts`
  - 后端响应类型、任务配置、定时配置、维护动作、设置结构都在这里。
  - 文件偏大，但属于类型集中定义，不急于拆分。

- `frontend/src/lib/objectPath.ts`
  - 设置页/Profile 编辑器用的嵌套对象读写工具。
  - 当前实现紧凑，职责清晰。

- `frontend/src/lib/taskWorkspace.ts`
  - 主界面任务配置草稿、任务项重命名、删除后选择、索引归一化等逻辑。
  - 这是主界面中最值得保留的业务抽象之一，没有重复造轮子。

- `frontend/src/lib/taskItemDefaults.ts`
  - 从 JSON 默认任务项创建任务条目。
  - 使用 `crypto.getRandomValues()` 生成 id，合理。

- `frontend/src/lib/jsonformsRenderers.tsx`
  - JSON Forms 自定义控件。
  - 负责布尔、文本、数字、枚举、动态枚举、原始数组编辑。
  - 已修正动态选项 `dynamicOptions(props)` 一次渲染调用两次的问题。
  - 仍保留渲染器专用 `FieldLabel`，因为这里的标签语义和 Settings/Profile 的字段标签不同；但 tooltip 已复用公共组件。

- `frontend/src/lib/usePolling.ts`
  - 新增公共轮询 hook。
  - 替代 `MainPage`、`SchedulePage`、`SettingsPage` 中重复的 `setInterval` 清理逻辑。

### 公共组件

- `frontend/src/components/ui/*`
  - 基础 UI primitives：button/card/input/select/checkbox/sidebar/scroll-area/tooltip。

- `frontend/src/components/DirtyActions.tsx`
  - 右下角 dirty save/reset 浮层。
  - 主界面、定时配置、设置页共享。

- `frontend/src/components/ConfirmDialog.tsx`
  - 删除、保存、更新、运行前确认共享。

- `frontend/src/components/FormFields.tsx`
  - 新增。
  - 提供 `HelpTooltip`、`FieldLabel`、`SectionTitle`、`TextField`、`NumberField`、`SelectField`、`CheckboxField`、`ReadOnlyLine`、`PathLine`。
  - 替代 `SettingsPage` 和 `ProfileEditor` 中重复实现的字段组件。

- `frontend/src/components/InsertionLine.tsx`
  - 新增。
  - 替代任务列表和数组编辑器中重复实现的拖拽插入线。

- `frontend/src/components/ProfileEditor.tsx`
  - 现在只保留 Profile 的业务字段布局。
  - 原本本地实现的 `FieldLabel`、`HelpTooltip`、`TextField`、`NumberField`、`SelectField`、`CheckboxField` 已删除，改为复用 `FormFields`。

- `frontend/src/components/PrimitiveArrayEditor.tsx`
  - JSON Forms 数组字段的编辑器。
  - 已改为复用 `HelpTooltip` 和 `InsertionLine`。
  - 仍然较大，主要原因是它同时处理自由输入、枚举选择、唯一约束、启用状态、拖拽排序和重命名。当前暂不拆，避免把一个高内聚控件拆碎。

### 主界面

- `frontend/src/pages/MainPage.tsx`
  - 管理任务配置列表、当前任务配置、任务项草稿、运行状态、删除确认。
  - 根据路由选择任务配置和子任务。
  - 本地草稿通过 `taskWorkspace` helpers 管理。
  - 运行状态轮询已改用 `usePolling()`。

- `frontend/src/pages/main/TaskListPane.tsx`
  - 任务配置切换/新增/删除。
  - 子任务列表、启用开关、重命名、删除、拖拽排序。
  - 已复用 `InsertionLine`。

- `frontend/src/pages/main/ConfigEditorPane.tsx`
  - 元数据编辑、Profile 选择、log level、JSON Forms 子任务参数编辑。
  - `isEqualConfig()` 仍用 `JSON.stringify` 做 dirty 比较；当前数据稳定、字段顺序由本端生成，可接受。
  - 后续若引入用户自由编辑任意 JSON，应换成稳定 deep equal。

- `frontend/src/pages/main/LogPane.tsx`
  - 手动运行和定时运行共用日志面板。

### 定时执行

- `frontend/src/pages/SchedulePage.tsx`
  - 现在只负责：
    - 列表/详情读取。
    - 草稿状态。
    - 运行控制。
    - save/reset/delete/create。
    - 选择 `settings/stats` tab。
  - 文件从约 797 行降到约 382 行。

- `frontend/src/pages/schedule/ScheduleLeftPane.tsx`
  - 新增。
  - 定时配置名称、绑定任务配置、启用开关、时间点列表、子任务启用清单。
  - 新增时间点 id 已由短 `Math.random()` 改为优先 `crypto.randomUUID()` 并检查已有 id，降低碰撞风险。

- `frontend/src/pages/schedule/ScheduleDetailPanels.tsx`
  - 新增。
  - 定时配置的设备/Profile、超时与重试、脚本变量、今日计数、近期运行。

发现并修正的真实行为问题：

- 之前在定时详情中更换绑定任务配置时，`draft.task_config` 会更新，但左侧子任务清单仍来自 `detail.task_config.task_items`。
- 结果是确认切换后，未保存前 UI 仍显示旧任务配置的子任务，容易误导用户。
- 已新增 `draftTaskConfig` 状态；确认切换后立即读取并使用新任务配置的 `task_items`。
- 保存、重置、重新读取详情时清空 `draftTaskConfig`，回到后端返回的权威详情。

其他修正：

- 重新读取详情时，如果原选中时间点不存在，回落到第一项。
- 定时运行状态轮询已改用 `usePolling()`。

### 设置页

- `frontend/src/pages/SettingsPage.tsx`
  - 管理框架设置、主题、Profile、maa-cli、维护动作、更新信息。
  - 已删除本地重复字段组件和重复 `TooltipProvider`。
  - 仍然约 658 行，主要因为该页面承载三组设置、更新信息、维护动作、validation 展示、主题即时应用。

评估：

- 当前最值得继续拆的是 SettingsPage，可按“框架与主题”“设备配置”“更新与资源”拆成三个设置卡片组件。
- 本轮先提取字段组件，保留页面结构，降低风险。

### 样式系统

- `frontend/src/styles.css`
  - 定义 Tailwind v4 主题 token、主题色变体、状态 pill、JSON Forms legacy surface、滚动条、break-anywhere。
  - 没发现明显通过大量叠加样式绕过已有组件的危险做法。
  - 存在一些页面级 `rounded-md border bg-background p-3` 重复结构，属于 section 容器样式；当前没有强行抽象，避免把语义不同的页面区块包装成泛化组件。

## 已实施修正清单

1. 新增 `frontend/src/components/FormFields.tsx`。
2. 新增 `frontend/src/components/InsertionLine.tsx`。
3. 新增 `frontend/src/lib/usePolling.ts`。
4. 新增 `frontend/src/pages/schedule/ScheduleLeftPane.tsx`。
5. 新增 `frontend/src/pages/schedule/ScheduleDetailPanels.tsx`。
6. `ProfileEditor` 删除重复字段组件，复用公共表单组件。
7. `SettingsPage` 删除重复字段组件和页面内 `TooltipProvider`，复用公共表单组件。
8. `PrimitiveArrayEditor` 复用公共 tooltip 和插入线。
9. `TaskListPane` 复用公共插入线。
10. `jsonformsRenderers` 复用公共 tooltip，并避免重复计算动态选项。
11. `MainPage`、`SchedulePage`、`SettingsPage` 改用公共轮询 hook。
12. `SchedulePage` 拆分为页面编排、左侧面板、详情面板。
13. `SchedulePage` 修复切换绑定任务配置后子任务清单仍显示旧配置的问题。
14. `SchedulePage` 修复刷新详情后可能保留无效选中时间点的问题。
15. `ScheduleLeftPane` 新增时间点 id 改为优先 `crypto.randomUUID()` 并去重。
16. `api.ts` 补强错误格式化。
17. `types.ts` 补齐 `Page` 类型中的 `tools`。

## 剩余风险与后续建议

- `SettingsPage` 仍偏大。建议下一步拆成 `FrameworkSettingsCard`、`ProfileSettingsCard`、`MaintenanceSettingsCard`。
- `PrimitiveArrayEditor` 功能复杂但高内聚。若后续继续膨胀，应拆出拖拽排序 hook、枚举添加器、自由输入行。
- `ConfigEditorPane` 与 `SchedulePage` 仍使用 `JSON.stringify` 做 dirty/deep equal。当前可用；若引入不可控对象键序，应替换为稳定 deep equal。
- 前端 bundle 仍触发 Vite 500 kB chunk warning。主要来自 React/JSON Forms/Radix 等依赖集中打包，不阻塞上线；后续可以用 lazy routes 或 manualChunks 优化。
- `frontend/src/lib/logs.ts` 的 `translateLogLine()` 当前是 identity，未被使用。若不计划做前端日志翻译，可以删除；若计划保留翻译扩展点，应在报告/注释中明确用途。

## 验证

- `cd frontend && npm run build`
  - 通过。
  - Vite 仍提示单 chunk 超过 500 kB，这是既有体积警告，不是本轮引入的构建失败。
- Vite preview + Playwright mock API smoke
  - 检查 `/tasks/test/items/startup`、`/schedule/daily-test`、`/settings`。
  - 桌面 `1440x1000` 与移动 `390x844` 视口均通过。
  - 未检测到水平溢出。
  - 截图保存在 `.codex/conversations/2026-06-30_2342-full-project-audit/scratch/`。
