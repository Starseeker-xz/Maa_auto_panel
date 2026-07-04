# Conversation Index

## Active Sessions（活跃引用 — 含架构决策或已知未解决问题）

- `2026-07-04_1115-review-cleanup`: 前后端死代码/兼容导入清理；移除内部包级 re-export 依赖，保留 `linux_maa.tools.game` 的 `python -m` 入口；前端收窄未使用导出和类型面；测试/构建通过。
- `2026-07-04_1047-audit-log-pipeline-audit`: 审计自 `7820a5b 模块化日志管线尝试` 以来的改动；发现 stop 退化为仅 SIGTERM、bounded log cursor 切片丢 attempt history、历史日志忽略 events/no-attempt schedule logs、`history/` 未忽略、`warning` 状态契约不一致等问题。
- `2026-07-04_1003-audit-log-pipeline`: 审计最近日志管线共通块逻辑并调整定时执行日志翻译/主题色高亮。
- `2026-07-04_clone-maa-sources`: 克隆 MAA 和 maa-cli 上游源码到 `external/` 目录以供参考。
- `2026-07-04_0341-log-template-framework`: 日志管线从 source template 重构为通用 source/block-rule 框架；事件改为普通 metadata 输入，前端日志 kind/status 放开为通用 block 渲染。
- `2026-07-04_0055-modularize-log-pipeline`: 可见日志管线破坏性模块化；统一 block-shaped `log_entries`，MAA 模板移到 `maa/log_templates.py`，原始文本保存仍归 Diagnostics。
- `2026-07-03_2049-review-latest-change`: 审查最近更改；确认测试/构建通过，发现审计文档中 `buttonVariants` 未使用导入说法已过时。
- `2026-06-30_1626-maa-stage-candidates`: `linux_maa.managed_params` 架构设计，Fight stage 候选和 Infrast plan 动态选项 API。
- `2026-06-30_1752-maa-cli-sequential-analysis`: 上游 maa-cli 调用模型分析（单 Assistant vs 逐子任务调用）。
- `2026-06-30_1934-scheduled-retry-architecture`: `retry_even_success` 元数据和定时重试编排架构。
- `2026-06-30_2318-gpu-ocr-research`: MaaCore GPU OCR 可用性测试 — 确认仅 CPU ONNX Runtime。
- `2026-07-01_1506-sse-log-delta`: SSE 增量推送模式（全量快照 + patch）和 `PROJECT_EXECUTION_POLICY.md`。
- `2026-07-02_1933-config-sync-ui-schema`: 前后端配置同步规则分析，废弃字段安全删除规则。
- `2026-07-02_2144-manual-stop-delay`: **已知未解决问题** — MaaCore 冷 ADB 60 秒超时根因分析与复现数据。
- `2026-07-03_0105-audit-log-module`: `RunLogBuffer` / `RunLogTranslator` 架构 — 所有 WebUI 可见日志的共享基础。
- `2026-07-03_1200-audit-and-refactor-codex`: **当前会话** — 项目全面审计、`.codex` 状态文件重构、会话归档。

## Archived Sessions（已归档 — 任务已完成，发现已汇入 project-history.md）

16 个已完成会话已归档至 `~/.codex/archived_sessions/linux-maa/`：
- `2026-06-26_1620-maa-cli-framework-docs` — 初始环境探测与 MAA 文档镜像
- `2026-06-26_1702-setup-maa-cli-test` — maa-cli/MaaCore 运行时安装
- `2026-06-26_1727-webui-config-runner` — 最小 FastAPI WebUI
- `2026-06-26_2030-separate-frontend` — React/Vite 前端分离
- `2026-06-29_1929-shadcn-sidebar` — shadcn 组件替换 Mantine
- `2026-06-29_2137-project-state-docs` — 项目文档刷新
- `2026-06-29_2232-config-editing` — JSON Forms 任务编辑器
- `2026-06-30_0014-task-editor-fixes` — 编辑器元数据和 UX 修复
- `2026-06-30_0124-config-save-delete` — 后端保存/删除/回收站
- `2026-06-30_1743-fix-infrast-plan-select` — Infrast 下拉标签修复
- `2026-06-30_2056-scheduled-execution` — 定时执行完整实现
- `2026-06-30_2342-full-project-audit` — 首次全量审计
- `2026-07-01_1312-explain-log-flow` — 日志翻译重构为领域包
- `2026-07-01_2153-manage-service-history` — Systemd 服务管理 + SQLite→JSON 迁移
- `2026-07-02_2245-tools-page` — 三栏工具页面
- `2026-07-03_1926-project-review` — 死代码清理

- `2026-07-04_1126-logpanel-spacing`: Fixed LogPane header/footer spacing: CardHeader default empty second grid row was removed for LogPane; footer error text right-aligned and padded away from details button. Build passed.
