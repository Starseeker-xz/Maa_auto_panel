# 项目历史与临时文件清理报告

Session: `2026-06-30_2342-full-project-audit`

## 清理结论

本轮清理将 `.codex` 从约 `447M` 压缩到清理完成时约 `292K`。最终验证阶段又在当前 session 的 `scratch/` 中保留了 6 张 Playwright UI smoke 截图，因此最终 `.codex` 约 `936K`。主要删除对象是历史 session 的 `scratch/` 原始材料：上游源码 checkout、ONNX/资源文件、截图、API payload、临时测试目录、dry-run 日志等。

保留对象是可读、可接力的状态文件：项目历史、项目 lessons、会话索引、各 session 的 `session.md`，以及当前 session 的记录。项目历史已从早期流水账压缩为当前架构 handoff，并修正了 scheduler 当前为 enabled 的事实。

## 清理前

- `.codex`: 约 `447M`
- 最大来源：
  - `.codex/conversations/2026-06-29_2232-config-editing/scratch/maa-src/`
  - 其中包含完整上游 MAA checkout、大型 `.git/objects/pack`、ONNX 模型、资源 JSON、文档图片。
- 其他来源：
  - 旧 Playwright 截图。
  - ADB/MAA dry-run 日志。
  - scratch API payload。
  - scratch 测试 repo。
  - `frontend/.codex` 下重复截图。
  - `debug/map/OF-1.jpeg` 本地调试图。

## 清理后

- 清理完成时 `.codex`: 约 `292K`
- 最终验证后 `.codex`: 约 `936K`
- 旧 session 的 `.codex/conversations/**/scratch/` 下不再保留文件。
- 当前 session 的 `scratch/` 保留 6 张 UI smoke 截图，约 `644K`。
- `TEMP/` 已删除。
- `debug/` 已删除。
- `frontend/.codex/` 已删除。
- `runtime/` 未清理，因为它是当前本地 maa-cli/MaaCore 运行环境和运行日志/cache/state 的所在地，不能当作无用历史删除。

## 保留规则

保留：

- `.codex/project-history.md`
- `.codex/project-lessons.md`
- `.codex/conversations/index.md`
- `.codex/conversations/<session-id>/session.md`
- 当前 session 目录和当前 session `scratch/` 中的 UI smoke 截图
- 根目录审计报告：
  - `BACKEND_AUDIT.md`
  - `FRONTEND_AUDIT.md`
  - `PROJECT_CLEANUP_AUDIT.md`

删除：

- `.codex/conversations/**/scratch/*`
- `frontend/.codex/`
- `TEMP/`
- `debug/`
- Python `__pycache__/`

## Ignore 规则更新

`.gitignore` 已新增：

```gitignore
.codex/conversations/*/scratch/
frontend/.codex/
debug/
```

已有规则继续忽略：

```gitignore
TEMP/
runtime/
downloads/
frontend/node_modules/
frontend/dist/
```

## 项目历史压缩

`.codex/project-history.md` 已重写为 compact handoff，保留以下 durable 事实：

- 当前仓库/配置/运行时状态。
- 产品方向。
- backend/frontend 当前架构。
- 当前 API surface。
- scheduler、managed params、maintenance、runtime 等核心特性。
- 本轮全项目审计修复。
- 当前 remaining risks。
- 最新验证命令结果。

删除或压缩的内容：

- 早期逐步实现流水账。
- 已被当前架构替代的计划项。
- 旧截图、旧日志、旧 scratch 路径。
- 与当前事实冲突的 scheduler disabled 旧记录。

## Git 视角

旧 scratch 和 `frontend/.codex` 曾被错误跟踪，因此清理后 `git status` 会显示大量 `D` 删除项。这是预期结果。未来提交时应把这些删除项一起提交，才能从版本库状态里彻底移除。

## 过程中的问题

- 第一次 scratch 清理命令错误使用了嵌套 `find -exec ... {} +`，GNU find 不允许同一个 `-exec ... +` 中出现多个 `{}` 占位。
- 已改用 `find ... -print0` 加 shell loop 清理。
- 该命令构造陷阱已记录到 `~/.codex/lessons.md`。
