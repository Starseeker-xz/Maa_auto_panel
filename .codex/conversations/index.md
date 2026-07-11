# Conversation Index

项目本地只索引仍有直接未来参考价值的会话。完成或已被后续结论覆盖的会话统一归档，不作为默认启动上下文。

## Active sessions

- `2026-07-11_1805-consolidate-audits`: 将全项目、路径与容器三份根目录审计整理为 `BACKEND_AUDIT.md`、`FRONTEND_AUDIT.md`；以后只维护这两份，代码修改仅将其作为需重新核对的参考。
- `2026-07-11_0203-separate-runtime-and-agent-doc`: 将 integration runtime 从 framework data 拆为独立根/容器卷，新增中文 Agent 项目说明；随后实现五类全局通知、通知设置/Toast/外部接口并拆分 Settings panels。
- `2026-07-11_0111-audit-container-plan`: 简单审计并提交当前大规模重命名、路径与优雅停机工作；随后复核正式 Docker 构筑前置条件。
- `2026-07-10_2207-graceful-shutdown`: 容器化优雅关闭已实现；FastAPI lifespan、SSE 主动退出、scheduler/四类 manager 共享 deadline、process group 清理和 status-0 SIGTERM 已通过真实 systemd 验证。
- `2026-07-10_1752-audit-data-paths`: 容器化前路径审计与实施；框架 data 已收敛到 `data/`，download cache 独立到 `cache/downloads/`，路径对象与本机最终布局已完成；项目未发布，不保留 migration CLI、layout version 或旧路径兼容。
- `2026-07-10_0416-full-project-audit`: 2026-07-10 完整审计的来源会话；结论已整理进当前前后端审计，不再直接作为最新代码事实。
- `2026-07-10_0004-complete-rename-maa-auto-panel`: 当前命名与路径迁移的权威会话。项目/包/CLI 为 Maa Auto Panel / `maa_auto_panel` / `maa-auto-panel`，框架 namespace 与本地状态目录已泛化。
- `2026-07-02_2144-manual-stop-delay`: 仍可能复发的 MaaCore 冷 ADB server 约 60 秒延迟复现与诊断。其他历史实现细节已汇入 project history/lessons。

## Archive

- 39 个完成、被覆盖或仅保留追溯价值的会话位于 `~/.codex/archived_sessions/maa-auto-panel/`。
- 归档包含早期建项、配置编辑、调度器、日志管线、run-manager 重构各阶段、并发仲裁、旧审计、清理与重命名中间会话。
- 需要追溯某项历史决策时按 session id 从归档读取；不要把归档会话重新批量加入启动上下文。
