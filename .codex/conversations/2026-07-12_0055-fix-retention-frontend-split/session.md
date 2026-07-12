# Session 2026-07-12_0055-fix-retention-frontend-split

## Scope and parallel boundary

- 主线：前端通用组件复用与 route/editor bundle 分拆。
- subagent：共享工作区修复后端 run memory/history retention；只用同目录 `backend-retention.md` 记录。

## Frontend implementation

- 新增 Radix/shadcn `ui/alert-dialog.tsx`、`ui/tabs.tsx` 与通用 `LazyBoundary`。
- `ConfirmDialog` 保持领域 props，内部迁移 AlertDialog；confirm preventDefault，受控 open 在异步完成前保持，busy 禁止 Escape/close。
- SettingsNavigation 使用 NavLink；ConfigEditorPane/Schedule center 使用 Radix Tabs；删除无调用的 `SegmentedControl`。
- 新增 `useInlineRename`，迁移 TaskListPane、ScheduleLeftPane、PrimitiveArrayEditor 的 rename/blur/Escape 状态；保留各领域 row/drag 行为，未制造巨型 EditableListRow。
- AppToolbar 原生 title 改为 Tooltip + aria-label。
- App 五类 page 使用 React.lazy；Main 仅 selectedTaskItem 存在时 lazy ConfigEditorPane，JSON Forms/schema 留在 editor chunk。LazyBoundary 处理稳定 fallback、route/item reset 与 reload recovery。

## Verification

- 实施前 build：单 JS 830.30 kB，gzip 260.46 kB，有 >500 kB warning。
- 最终 build：入口 413.62 kB/gzip 132.00 kB；editor 289.90 kB/gzip 94.29 kB；route chunks 1.58–27.37 kB；无 chunk warning。
- 浏览器 smoke：Settings 首屏不请求 ConfigEditorPane；基础/框架/主题 NavLink 正常；AlertDialog Escape 正常；Schedule Tabs ArrowRight 选中统计；最终通过。
- smoke 脚本首次从 session scratch `import playwright` 失败，因为 Node ESM 按脚本目录解析；改为显式引用 frontend node_modules。首次 Tabs 断言同步读取早于 state commit，改为 waitForFunction 后确认真实交互通过。
- 合并后后端 `101 passed`，compileall 通过；前端 TypeScript/Vite build 通过；`git diff --check` 通过。

## Backend retention summary

- 终态释放 plan/callback；manager 仅保留 active 或最近 terminal snapshot。
- run/retry 联合按整 run 淘汰；active 永保留；手动删除 active 返回 409。
- 先写索引再级联 history/event/stream/generated-config/MaaCore owned data；unknown/shared artifact 保留；diagnostics 清 orphan 并保护 retained owned paths。

## Environment effects

- 确认四类 manager 均无 active run后重启 `maa-auto-panel-webui.service`；最终 MainPID 37484，service active，四类 current 均 idle。
- 历史 run `84887fbd6973` 回读 succeeded，12 个结构化日志块。
