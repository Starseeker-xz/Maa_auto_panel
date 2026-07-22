# Conversation Index

这里只索引仍含不可替代探索、原始数据或尚未被权威文档完全替代的会话。完成且结论已提升到审计/history/lessons 的会话位于全局归档；不会因“可能继续旧对话”而保留。

## Retained sessions

- `2026-07-14_2122-audit-scheduler`: scheduler 正确性核实、跨游戏日产品语义、retry 术语统一、共享 `MaaRetrySession` 实现，以及 MaaFramework ProjectInterface/Tasker 对未来通用 WebUI 边界的官方资料结论。
- `2026-07-14_2057-full-code-audit`: 当前完整代码/架构/测试审计；含 coverage data、前端子代理逐项证据及本轮持久化整理记录。
- `2026-07-14_0244-optimize-log-template-migration`: 保留 174 个 raw stdout/stderr、7,866 行模板覆盖审计的耐久结论 `raw_template_audit.md`；用于后续模板规则取舍，不作为当前架构说明。
- `2026-07-14_0145-audit-gui-tools`: 保留 MAA GUI/Core/maa-cli 上游探索；是下一轮“公招识别 + 牛杂”参数、副作用、结果边界和动态限时条目的详细依据。
- `2026-07-11_0111-audit-container-plan`: 保留隔离容器构筑/运行验收和 OpenCV SONAME 混合 runtime 的原始探索；当前容器边界以 `docs/BACKEND_AUDIT.md` 为准。
- `2026-07-02_2144-manual-stop-delay`: 保留冷/热 ADB server 两组原始复现 JSON；用于 MaaCore 60 秒 `adb devices` 延迟再次出现时对照。

## Archive

- 其他已完成、被后续实现覆盖或只有时间线价值的会话位于 `~/.codex/archived_sessions/maa-auto-panel/`。
- 需要追溯历史实现时按 session id 从归档读取；不要批量恢复到项目 conversation index。
