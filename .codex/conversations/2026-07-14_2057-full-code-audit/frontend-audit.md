# 前端完整审计（子代理）

父会话：`2026-07-14_2057-full-code-audit`

子代理：`frontend-audit`

范围：`frontend/` 全部源码、构建配置和依赖，并交叉核对 `src/maa_auto_panel/web/routes/`、`run_manager/router.py`、`web/sse.py`、`tools/manager.py` 等前后端契约。只读审计，未修改业务代码。

## 当前架构

```text
main.tsx
└─ BrowserRouter
   └─ App / AppShell
      ├─ 固定 Sidebar（主任务 / 定时 / 工具 / 设置）
      ├─ NotificationCenter（独立 notifications SSE、Sonner、Sheet、Scrcpy launcher）
      └─ route lazy boundary
         ├─ MainPage
         │  ├─ Config/task workspace + per-config drafts
         │  ├─ TaskListPane
         │  ├─ lazy ConfigEditorPane
         │  │  └─ JSON Forms + 本地七类 MAA schema + 自定义 shadcn renderers
         │  └─ LogPane
         ├─ SchedulePage
         │  ├─ schedule overview/detail/draft/history
         │  ├─ ScheduleLeftPane / ScheduleDetailPanels
         │  └─ LogPane
         ├─ ToolsPage
         │  ├─ 服务端 ToolDefinition 驱动的列表/表单
         │  └─ LogPane
         └─ SettingsPage / ThemeSettingsPage
            ├─ framework/profile/maa-cli/notification drafts
            ├─ maintenance run
            └─ panels + FormFields

API / state
├─ lib/api.ts：手写 fetch functions + 手写 wire types (lib/types.ts)
├─ lib/runStream.ts：run SSE reset/patch 合并算法
├─ 各页面：各自 snapshot → EventSource → error/busy 生命周期
└─ 后端：FastAPI routes + GenericRunManager state/SSE

UI primitives
├─ shadcn/Radix：AlertDialog, Accordion, Tabs, Select, Sheet, ScrollArea,
│              Checkbox, Tooltip, Button, Card, Sidebar
├─ Sonner：Toast
└─ 领域组件：DirtyActions, RunStopButton, LogPane, PrimitiveArrayEditor 等
```

总体判断：前端的页面 lazy 边界、日志 patch 模型、通用 `LogPane`/`RunStopButton`、AlertDialog/Tabs/Sheet/Sonner 复用方向正确。最值得改的不是重写 UI，而是建立两个真正的通用边界：（1）run snapshot/SSE/action hook；（2）服务端下发的 integration/action/editor descriptor。当前不少专项逻辑正是因为缺少这两个边界而散落在页面和本地 JSON 中。

## 发现（按优先级）

### P1 — 工具页切换选择后可在已有工具运行时再次点击运行

- 证据：`frontend/src/pages/ToolsPage.tsx:77-80` 将不属于当前选中工具的全局 run 经 `runForTool` 投影为 `idle`；`ToolsPage.tsx:92-98` 的 `handleRun` 只检查 `selectedTool`/`busy`，不检查原始全局 run；`ToolConfigPane.tsx:24-25,43-48,59` 又仅依据投影后的 run 决定表单和运行按钮是否禁用。
- 结果：工具 A 运行时选中工具 B，B 的表单和“运行”重新启用，可以发送第二次 start。后端 manager 大概率拒绝并显示冲突，但 UI 已违反单 manager 的全局活跃约束；且此时停止按钮也不可用，用户必须重新选中 A 才能停止。
- 建议：展示态可继续按 tool 过滤日志，但 action availability 必须使用未经筛选的全局 run。给 `ToolConfigPane` 单独传 `managerActive`/`activeToolId`，或由通用 live-run hook 输出 `globalActive` 与 `visibleRun` 两个明确概念。

### P1 — 编辑器注册表完全硬编码在前端，已成为 integration 通用化的主要阻碍

- 证据：`frontend/src/lib/taskSchemas.ts:3-33` 静态 import 并登记七种 MAA task；`taskItemDefaults.ts:1-27` 与 `config/task-item-defaults.json` 又维护另一份可新增 task 清单和默认值；`TaskListPane.tsx:266-271` 只允许从该本地清单新增。未知类型虽能从磁盘读入，但 `ConfigEditorPane.tsx:113-152` 只能显示“没有接入模板”，无法编辑 params。
- 重复/漂移：task type、中文名、默认 params、JSON schema、general/advanced 分组分别存在于多个前端文件，并与 maa-cli schema/后端领域知识重复。增加第二 integration 或上游新增 task 必须修改前端 bundle；服务端无法注册一个通用 action 后即被 UI 使用。
- 建议：建立服务端 `task/action editor descriptor`：`integration`, `type`, `title`, `defaults`, JSON Schema/UI schema（或字段 descriptor）、动态 option source。前端只保留通用 renderer registry；MAA 专用 descriptor 留在 MAA 领域后端或可版本化资源中。先迁移现有七类验证形状，再用第二 integration 验证，而不是再加第八个静态 import。

### P1 — 三类页面未保护未保存草稿，跨主路由会静默丢失

- 证据：Main 的 drafts 只存在 `MainPage` state（`MainPage.tsx:56-59`），Schedule draft 在 `SchedulePage.tsx:49-50`，Settings draft 在 `SettingsPage.tsx:35-38`；`DirtyActions` 只显示保存/复位浮层，没有 `beforeunload` 或 React Router blocker。离开对应 lazy route 会卸载页面并销毁 state。
- 影响：Main 内部切换 task config 会保留 `draftsByConfig`，但从主任务跳到定时/工具/设置会丢失全部 task drafts；Schedule/Settings 同理。没有确认提示。
- 建议：抽取 `useUnsavedChangesGuard(dirty)`，组合 Router blocker + `beforeunload`，确认 UI 复用现有 AlertDialog。若产品明确不做导航保护，则至少把草稿提升到 route 外的 workspace store；不能仅依赖浮动按钮暗示用户。

### P1 — 缺少任何前端自动化测试，且高风险纯逻辑没有独立验证入口

- 证据：`package.json` 只有 dev/build/preview；没有 test script 或测试文件。Playwright 只是 devDependency。现有 production build 能证明类型/打包，不覆盖 SSE reconnect/patch、draft 合并、工具全局活跃态、通知去重等。
- 建议：先为 `lib/runStream.ts`、task workspace、retry count/storage、tool run projection 建纯单测；再用少量 Playwright 覆盖 dirty navigation、工具切换期间的 action disabled、SSE reset/patch/reconnect。EventSource 页面不要等待 `networkidle`。

### P2 — 四处重复实现 live run snapshot + SSE 生命周期，错误处理已出现差异

- 证据：`MainPage.tsx:154-185`、`SchedulePage.tsx:114-145`、`ToolsPage.tsx:44-75`、`SettingsPage.tsx:71-102` 基本逐行重复：GET snapshot、构造带 cursor URL、EventSource、JSON parse/apply、相同 reconnect error 文案策略与 cleanup。
- 已有差异：Main 的 stop handler（`MainPage.tsx:247-251`）没有 busy guard/catch，而 Tools/Schedule 各自维护 busy/catch；四处 `JSON.parse` 的异常策略也不统一。继续新增 action/integration 会复制第五份。
- 建议：抽取 `useLiveRun({ getSnapshot, eventsUrl, connectionError })`，返回 `run`, `connectionError`, `setRun`；动作请求仍由领域页持有或用一个薄 `useRunActions`。不要做识别 manual/schedule/tool 的巨型 hook；它只处理 opaque RunState 协议。

### P2 — 运行详情从中文可见日志反向解析领域数据，是脆弱的 MAA 专项耦合

- 证据：`frontend/src/pages/main/LogPane.tsx:171-188` 搜索固定中文前缀“选择战斗关卡:”和“选择基建计划:”来构造详情。
- 影响：日志模板改词、翻译、格式或 integration 变化即静默丢失详情；展示日志本不应成为状态/结果权威。它也让通用 `LogPane` 内含 MAA 领域词汇。
- 建议：plan/result 在 run/retry metadata 或 typed artifacts 中写入结构化 selections；LogPane 只通过通用 detail/artifact descriptor 展示。MAA 负责产生 descriptor，不让前端解析人类文本。

### P2 — Profile 表单存在近乎逐字段复制的两份实现

- 证据：`components/ProfileEditor.tsx:10-79` 与 `pages/settings/panels.tsx:60-99` 的连接类型/config、ADB path/address、touch mode、GPU/CPU OCR 和三项 checkbox 基本相同，仅外层 panel/path/validation 不同。
- 风险：已经出现 help 文案轻微差异；字段增删/默认值调整很容易只改一边。Schedule 内嵌 profile 与 Settings 默认 profile 会逐渐产生不同语义。
- 建议：`DeviceSettingsPanel` 组合 `ProfileEditor`，将 path/validation 放在外层；或抽一个无 panel 的 `ProfileFields`。保留不同领域容器，不复制 field definition。

### P2 — Tool descriptor 是半实现契约：`kind` 和 `description` 下发但前端完全忽略

- 证据：后端 `tools/manager.py:30-44,47-61` 定义/序列化 `ToolField.kind` 与 `ToolDefinition.description`；前端 types 也声明它们（`lib/types.ts:456-469`），但 `ToolConfigPane.tsx:39-50` 对所有 field 无条件渲染文本 Input，`ToolListPane`/`ToolConfigPane` 都不展示 description。
- 当前只有一个 text 字段，因此暂未触发，但新增 number/select/boolean/危险动作确认时 descriptor 会看似支持、实际失效。
- 建议二选一：若短期只需 text，删除 `kind` 并把 contract 收窄，description 明确展示；若马上扩展公招/牛杂工具，则定义受控 field union（text/number/select/checkbox + options/min/max/side-effect/retry policy）和 renderer registry，避免每个工具写专用 form。

### P2 — 动态字符串选项 API 失败时并没有注释承诺的自由文本 fallback

- 证据：`useTaskDynamicOptions.ts:24-26` catch 注释称保留 free-text fallback；`jsonformsRenderers.tsx:35-40` 发现 `x-optionsSource` 后始终进入 `DynamicSelectControl`；后者 `jsonformsRenderers.tsx:91-127` 即使 dynamic/enum 均为空仍渲染无选项的 Radix Select。Infrast filename/plan 都是 string 动态字段。
- 影响：动态接口暂时失败或返回空数组时，用户无法输入/修复文件名或计划值。Primitive array 的 fallback 确实可自由输入，但 string 分支不行。
- 建议：无 options 时回退 `TextControl`；更理想的是引入 shadcn Command + Popover 组合成可输入 combobox，同时允许合法自定义值。这是适合组件库 primitive 的场景，不应手搓键盘/焦点行为。

### P2 — NotificationCenter 只限制持久化数组，运行期 Set 仍无界增长

- 证据：recent 有 `MAX_RECENT=100`，localStorage 写入在 `NotificationCenter.tsx:186-187` 截到 500；但 `readIds`、`deletedIds` state 和 `toastedIds.current`（lines 29-33, 64-70, 94-112）不断添加且从不裁剪。写入裁剪不会反向替换内存 Set。
- 影响：作为长期打开的 panel，事件/删除越多内存集合越大；与项目其余有界日志策略不一致。
- 建议：统一 `boundedIdSet`，每次 state 更新就裁到上限；toastedIds 也按 recent/replay horizon 裁剪，或依赖服务端单调 sequence 水位而非永久记住每个 id。

### P2 — Sidebar 的 schedule 副本缺少明确 invalidation，重命名后可长期显示旧名称

- 证据：App 自己持有 schedules 并仅以 `location.pathname` 变化触发 `listSchedules`（`App.tsx:75-85`）；SchedulePage 保存后只刷新自身 overview/detail。原地修改当前 schedule 名称时 pathname 不变，App sidebar 不刷新。
- 建议：把 schedule catalog 查询提升为共享 store/query hook，由 create/save/delete 主动 invalidate；或最小化地由 SchedulePage 成功 mutation 后触发 App callback。不要靠路由变化充当数据 invalidation。

### P2 — 手写 RunDetails 浮层重复了 Popover 的交互基础设施

- 证据：`LogPane.tsx:81-92,103-120` 用 absolute div + 本地 boolean 实现浮层；没有 outside click/Escape、焦点管理、`aria-controls`/popover role，也可能被 Card overflow 边界裁剪。
- 建议：通过项目 `components.json` 加入官方 shadcn Popover，按钮做 trigger、详情做 content。领域代码只保留 detail rows。现有 Confirm/Dialog/Tabs/Sheet/Sonner 已正确复用，无需替换。

### P2 — 前后端 wire types 完全手写且大量 `Record<string, unknown>`，契约漂移只能在运行时暴露

- 证据：`lib/api.ts` 对所有 endpoint 手写返回泛型；`lib/types.ts` 514 行手工镜像后端 dict/Pydantic/dataclass。保存 settings/schedule/tool 等关键 payload 又降级为宽 dict。后端虽使用 Pydantic 输入，但输出多为 `dict[str, object]`，OpenAPI 也无法给出精确 response schema。
- 建议：先给高价值 endpoint 增加明确 response model/discriminated union（RunState patch、ToolDefinition、Settings/Schedule），再生成 TypeScript types；表单 draft/display model 仍保留前端独立类型。不要试图一次生成所有内部类型。

### P3 — 明确死代码、死字段和静态检查缺口

- `frontend/src/lib/usePolling.ts` 无任何引用，整个 hook 是死代码。
- `taskSchemas.ts:17-22,39-46` 返回 `generalKeys`/`advancedKeys`，仓库无消费者。
- `SchedulePage.tsx:33` 导入 `cn` 未使用；`npx tsc --noUnusedLocals --noUnusedParameters` 可复现 TS6133。默认 tsconfig 未开启 noUnused，因此 production build 仍通过。
- 建议：删除上述死代码/字段；在 CI 增加 noUnused（可先修净后开启），再考虑 knip 检查文件/export/dependency 级死代码。

### P3 — Schedule overview 卡片仅支持鼠标

- 证据：`SchedulePage.tsx:352-370` 给 Card div 绑定 onClick，但没有 `role`、tabIndex 或键盘处理。
- 建议：卡片内容用 React Router `NavLink`/Link 作为真正导航元素并由 Card 负责样式；这是标准 HTML/Router primitive，不需自制 role/键盘分支。

### P3 — Radix 依赖入口混用，维护面不必要地扩大

- 证据：checkbox/select/scroll-area/slot/tooltip 使用五个 `@radix-ui/react-*` 直接依赖；accordion/alert-dialog/sheet/tabs 又从 `radix-ui` umbrella 导入。并非当前 bundle bug（tree shaking 正常），但生成组件升级时容易形成两种版本/风格。
- 建议：下一次更新 shadcn primitives 时统一按当前 `components.json`/shadcn CLI 生成风格，不必为了此项单独大改。

## 不建议修改的部分

- `ConfirmDialog` 已基于 shadcn AlertDialog，不是手搓 modal；`DirtyActions` 作为领域确认编排合理。
- `RetryLogList` 已基于 Radix Accordion；配置/统计已用 Tabs；通知已用 Sheet + Sonner；这些不应重新造轮子。
- `PrimitiveArrayEditor` 和两类领域列表虽有原生拖放重复，但 shadcn/Radix 本身没有 sortable primitive。若要修键盘排序，应一次性选择成熟 sortable 库统一迁移，不应以“组件库复用”为名手写更多键盘分支。
- Schedule 左栏的可调分隔条是领域布局行为，Radix Separator 只提供视觉/语义分隔，不负责 resizing；当前自行实现可接受，但应补 pointer-cancel/unmount 恢复 body cursor 的测试。

## 推荐实施顺序

1. 修工具全局活跃态、动态 select fallback、schedule 卡片键盘与 dead code（低风险 correctness）。
2. 抽 `useLiveRun` 和 retry-count/local-storage 小工具；补纯测试后迁移四页。
3. 合并 ProfileFields；用 shadcn Popover 替换 RunDetails 手写浮层；给 dirty pages 加统一 guard。
4. 设计服务端 action/editor descriptor，并让 tools 与 task editor 共用字段 renderer registry；用下一批“公招/牛杂”需求验证 descriptor，而不是继续增加页面专用字段。
5. 为高价值 FastAPI response 建模型并生成 TS wire types，逐步缩小 `Record<string, unknown>`。

## 验证记录

- `npm run build`：通过；Vite 6.4.3，2232 modules；入口 JS 416.61 kB / gzip 133.22 kB；ConfigEditorPane 289.90 kB / gzip 94.29 kB；无 500 kB warning。
- `npm audit --omit=dev`：0 vulnerabilities。
- `npx tsc --noEmit --noUnusedLocals --noUnusedParameters`：失败，仅报告 `src/pages/SchedulePage.tsx(33,1): 'cn' is declared but its value is never read`。
- 无 test script / unit test / component test；未启动服务、未修改环境。

## 值得提升为 project lesson 的陷阱

1. 同一 manager 的 run 可以按领域实体过滤“显示日志”，但 start/stop availability 必须依据未过滤的全局 manager state；否则切换实体后会把已有运行伪装成 idle。
2. `x-optionsSource` 动态字段必须定义 API 失败/空结果的真实交互 fallback；string Select 没有 options 时并不等于 free-text fallback。优先使用成熟 combobox primitive。
3. 通用 LogPane 不得从人类可见/翻译后的日志文本反解析领域状态；详情必须来自结构化 metadata/artifact descriptor。
4. descriptor 字段一旦进入前后端契约就必须有 renderer/行为消费者；否则删除未实现的 kind 比保留“看似通用”的半成品更安全。
