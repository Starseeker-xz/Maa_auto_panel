# Session 2026-07-11_2113-audit-frontend-reuse-bundle

- 任务：审计前端通用组件复用与 bundle 拆分。

## 结论

- ConfirmDialog 是最高优先复用缺口，应迁移 shadcn AlertDialog。
- SegmentedControl 混合路由导航与 tabs 且 tab 键盘语义不完整，应按 nav/Tabs/ToggleGroup 分流。
- 三类可编辑拖拽列表存在状态和键盘处理重复，建议先抽 hook 再抽行组件。
- App 静态导入所有页面；Main 静态带入 JSON Forms、renderers 与七份 schema。建议 route lazy，再 editor lazy，最后按测量决定 schema lazy。
- 按用户要求未运行 frontend build，也未验证旧 bundle 数字。

## 修改

- 更新 docs/FRONTEND_AUDIT.md 两个 P1 条目，未改前端产品代码。

## 检查

- `git diff --check -- docs/FRONTEND_AUDIT.md`：通过。
