# Conversation Index

项目本地只索引仍有直接未来参考价值的会话。完成或已被后续结论覆盖的会话统一归档，不作为默认启动上下文。

## Active sessions

- `2026-07-14_0051-audit-maa-log-templates`: 只读审计 MAA 日志模板与通用管线边界；确认纯文本 output 投影无生产消费者、active block 记录上限未即时执行，并提出 pipeline-owned 结构化追加重构方向。
- `2026-07-14_0004-optimize-maa-log-format`: 优化 MAA 日志翻译、详情四字符缩进和局部富文本强调；汇报平台噪声折叠为单条成功提示。

- `2026-07-13_2243-frontend-retry-block`: 实现完整 retry 日志折叠层、持久化富文本摘要与 MAA 逐次任务结果展示；展开状态只响应首次进入、新 retry 和用户操作。
- `2026-07-13_1541-review-incomplete-session`: 复核并完成上一 run-architecture 会话收尾；实现 durable-first 终态提交、MAA 领域 debug cleanup、完整 channel diagnostics 与 corrupt-state 边界，完整后端 119 passed。
- `2026-07-13_1500-audit-run-architecture`: 审计并实施 run core/path/异常重构；process/manager/store/diagnostics 已脱离 MaaRuntime，新增通用 retry-scoped 增量文件诊断捕捉与五类应用异常 handlers；其“110 tests passed”记录已由后续复核纠正。

- `2026-07-12_0216-fix-scrcpy-url`: 修正 scrcpy URL 协议中 request_id 的 UUID 生成与文档约定。
- `2026-07-12_0125-toolbar-scrcpy-notifications`: 审计并调整 Toolbar 尺寸/分隔、通知删除按钮 focus 行为，并设计本地 scrcpy URL 协议。
- `2026-07-12_0055-fix-retention-frontend-split`: 修复后端 run-aware retention；前端迁移 AlertDialog/NavLink/Tabs/rename hook/Tooltip，并完成 route + editor lazy 分块、构筑与浏览器 smoke。
- `2026-07-11_2113-audit-frontend-reuse-bundle`: 完整盘点前端通用组件复用与静态 import graph；确认 AlertDialog、segmented 语义与三类 sortable list 是主要复用缺口，bundle 建议按 route lazy → Main editor lazy → 按测量决定 schema lazy 拆分。
- `2026-07-11_2113-audit-retention`: 只读确认 run retention P1：manager 内存与 history JSON 无界，diagnostics/generated configs 已有独立 retention 但未与 run-aware deletion 协调。
- `2026-07-11_2113-fix-persistent-paths`: 并行审计并处理后端持久路径逻辑根问题，范围为 store、diagnostics、trash、artifact 与 download manifest。
- `2026-07-11_2105-audit-stream-no-newline`: 无换行 reader P0 已修复，并保持历史日志逻辑行分块；同轮完成持久路径 P2 本机迁移、完整验证与 systemd 切换。
- `2026-07-11_2059-audit-stream-no-newline`: 复核后端统一进程执行器的无换行阻塞 P0；当前实现仍可复现 1 秒 timeout 被拖到子进程 3 秒自然退出且未标记超时，修复应采用 non-blocking bytes + incremental decode/line buffering。
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
