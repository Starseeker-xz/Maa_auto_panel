# Project History

面向无上下文后续会话的近期交接。这里只记录当前聚焦、近期变化和仍有效的 handoff；完整架构与长期整改清单见：

- `docs/BACKEND_AUDIT.md`
- `docs/FRONTEND_AUDIT.md`

置信度：Confirmed / Likely / Hypothesis / Unknown。

## Current focus

- Confirmed (`2026-07-14_2057-full-code-audit`): 完整代码审计已重写前后端审计文档。当前无 P0；后端优先处理 scheduler missed-window、APK manifest/身份验证、资源等待 shutdown 语义、open-retry checkpoint；前端优先处理工具 global-active 投影、动态 option fallback、草稿导航保护和测试基础设施。
- Confirmed (`2026-07-14_2057-full-code-audit`): 当前 142 个后端 cases 在约 8–10 秒内通过，总覆盖约 74%。测试数量不是性能问题；建议只直接删除/并入约 2–4 个 forwarding/重复用例，再通过 table-driven cases 与共享 fixtures 降低测试代码维护量。scheduler service、MAA runner、game updater 的覆盖比日志/协调器明显不足。
- Confirmed (`2026-07-14_2057-full-code-audit`): Ruff 当前发现 11 项：`GenericRunManager` 缺 `Callable` import、contracts 的 `RunAttempt/RunCallbackAPI` annotation 无法解析，以及 notifications 一个 unused import。`typing.get_type_hints()` 可复现 NameError；pytest/compile/build 仍通过。
- Confirmed (`2026-07-14_2057-full-code-audit`): `AGENTS.md` 已明确审计文档、project history、conversation index 的分工，并增加测试精简准则。`.codex` 只保留仍含不可替代探索/数据的旧会话，其余实现时间线归档。

## Recent changes still relevant

- Confirmed (`2026-07-14_1304-investigate-9am-schedule`): MAA 日志模板按 retry 热读取；可解码 TOML 片段级容错，整份损坏时使用 last-known-good/plain fallback。可见日志配置失败不能阻止外部命令或 run 终态收尾。
- Confirmed (`2026-07-14_0244-optimize-log-template-migration`): 可见日志采用通用 `TemplateBlockRuntime`、per-source preprocess state 和声明式 TOML blocks。raw stderr 的 `MaaTaskResultCollector` 仍是任务结果权威，不依赖展示模板。原始 174 个日志文件的覆盖审计保留在该会话。
- Confirmed (`2026-07-13_1541-review-incomplete-session`): `GenericRunManager` 已保持领域无关，终态 durable-first/live-second；process/store/diagnostics 已脱离 `MaaRuntime`。MAA debug cleanup、MaaCore 增量捕捉和 task result 保留在 MAA 领域。
- Confirmed (`2026-07-12_0055-fix-retention-frontend-split`): run-aware retention 以整 run 为 ownership 单元；前端已按 route 和 JSON Forms editor 分块，现有构筑无 >500 kB warning。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): writable roots 分为 framework `data/`、integration `runtime/`、download `cache/` 和独立 ADB credentials；持久引用使用 `framework:`、`runtime:`、`downloads:` 逻辑根。

## Next feature handoff

- Confirmed (`2026-07-14_0145-audit-gui-tools`): 用户下一轮 tools 范围为“公招识别 + 牛杂”，排除干员识别、仓库识别、牛牛抽卡和牛牛监控。完整上游调用链、参数、五个 Custom 入口、副作用、Recruit callback 缺口与动态限时条目探索保留在该会话 `session.md`。
- Confirmed: Recruit calc-only 使用 `times=0, confirm=[-1]`，不会最终确认招募，但可能设置时间并点击 Tags；当前 maa-cli 丢失 GUI 所需的组合/候选干员明细，实施完整结果页前必须建立 MAA 领域结构化 result 边界。
- Confirmed: 四个商店类 Custom 工具会真实消费资源，不能无条件继承通用 1–50 retry 控件；UI/descriptor 必须声明副作用和 retry policy。
- Unknown: 首轮是否同时实现 Maa API 动态下发的限时 miniGame 条目；若会改变 registry/descriptor 结构，应先确认产品范围。

## Environment and deployment

- Confirmed (`2026-07-14_2057-full-code-audit`): 本轮只修改审计、AGENTS 和 `.codex` 状态；未修改产品代码，未重启 systemd，未运行 Docker、MAA 或设备任务。
- Confirmed: 开发/裸机 systemd 与未来 Compose 实例不得同时连接同一设备或共享 data/cache/ADB state；当前框架/协调/store 仍是单进程模型。
- Confirmed: 产品威胁模型仍为可信内网、单用户；不因本轮审计引入认证、RBAC、数据库、微服务或动态第三方 Python 插件。
- Confirmed (`2026-07-11_0111-audit-container-plan`): 隔离容器安装曾发现官方 stable runtime 的 OpenCV SONAME 混合风险；`maa version` 不能替代真实设备 plugin smoke。原始容器探索会话继续保留。
