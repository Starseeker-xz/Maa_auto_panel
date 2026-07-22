# Project History

面向无上下文后续会话的近期交接。这里只记录当前聚焦、近期变化和仍有效的 handoff；完整架构与长期整改清单见：

- `docs/BACKEND_AUDIT.md`
- `docs/FRONTEND_AUDIT.md`

置信度：Confirmed / Likely / Hypothesis / Unknown。

## Current focus

- Confirmed (`2026-07-21_1125-check-ad3-stage-support`): Fight 编辑器已将 `StageActivityV2` 收敛为带开放元数据的推荐集，而非 MaaCore 能力白名单；未知自定义关卡去除首尾空白后原样尝试，已知活动/资源关仍按窗口/星期解析。通用可创建 Popover 支持列表搜索、自定义、API 失败 fallback；常驻关 GUI 中文别名来自独立随包 JSON。行编辑/删除已共享无边框 action 基线，Popover 不再覆盖 Button slot 或在 pointer 关闭后残留焦点态。推荐 API 现以 `cache/maa/StageActivityV2.json` 为框架自有缓存，10 分钟 ETag 刷新、失败回退旧文件；maa-cli 的 `runtime/maa/cache/maa` 仅作只读 fallback，避免混淆框架与功能提供方所有权。162 tests、Ruff、compileall、前端 build、wheel data、配置生成和 Playwright smoke 均通过；推荐刷新无设备 smoke 已通过。
- Confirmed (`2026-07-20_0910-reorganize-storage`): 诊断已按实际提供方分组：`data/debug/framework` 只含 `framework.log` 和 `events`，MAA、scheduler scripts、tools 分别位于 `data/debug/maa`、`data/debug/scheduler`、`data/debug/tools`。provider scope 逐段拒绝空段、`.`、`..`、路径穿越及保留的 `framework` 命名空间。
- Confirmed (`2026-07-20_0910-reorganize-storage`): 运行存储已收敛到顶层 `data/run-history`。`recent-run-records.json` 是轻量列表和中断恢复权威，scoped per-run JSON 是 retry 详情唯一来源；`run-retries.json`、`log_entries_file` 和旧 `/api/history/runs` 已删除。新 API 为 `/api/runs/history...`。
- Confirmed (`2026-07-20_0910-reorganize-storage`): 所有面板发起的 maa-cli/MaaCore 命令 cwd 已固定为 `runtime/maa/state/maa`，因此 MaaCore 相对产物 `debug/map/<stage>.jpeg` 留在 MAA 原生 debug retention 树；用户 scheduler scripts 仍使用 repo root。
- Confirmed (`2026-07-20_0910-reorganize-storage`): retry 详情写失败现在记录 framework diagnostic 并继续领域 retry loop；run 终态仍 durable-first/fail-closed。152 tests、Ruff、compileall、前端 build 均通过。
- Confirmed (`2026-07-15_2233-audit-last-session`): 已复核上一 session 的 retry 术语统一与 `MaaRetrySession` 抽取，143 tests、Ruff、compile、type-hint 解析均通过，未发现阻断性功能回归。剩余是一个低风险可空类型注解不准确，以及 scheduled 非 skip/shared finish 边界尚无直接测试；`BACKEND_AUDIT` 对 adapter 覆盖和验证来源的表述应收紧。
- Confirmed (`2026-07-14_2122-audit-scheduler`): 当前无 P0；后端优先处理 scheduler missed-window/reservation、APK manifest/身份验证和资源等待 shutdown 语义。跨游戏日按完成时当前日计数并停止追逐旧日欠账是明确产品语义，不是 attribution bug。
- Confirmed (`2026-07-20_0910-reorganize-storage`): 当前 152 个后端 cases 在约 6–10 秒内通过，总覆盖基线仍约 74%。scheduler scanner、game updater 的关键恢复/损坏路径仍需补测。
- Confirmed (`2026-07-14_2122-audit-scheduler`): run contracts 已统一 retry 术语，`RetryContext/RetryDecision/RunCallbackAPI` 位于无环 `run_manager/context.py`，`typing.get_type_hints()` 和 Ruff 均通过。manual/scheduled 已共享 `MaaRetrySession` 的配置物化、collector 和 MaaCore 捕捉，各自保留 task selection/final policy。
- Confirmed (`2026-07-14_2057-full-code-audit`): `AGENTS.md` 已明确审计文档、project history、conversation index 的分工，并增加测试精简准则。`.codex` 只保留仍含不可替代探索/数据的旧会话，其余实现时间线归档。

## Recent changes still relevant

- Confirmed (`2026-07-14_2122-audit-scheduler`): MaaFramework 官方 ProjectInterface V2 已提供 task/entry、group、option、preset、controller/resource applicability 和 pipeline override 的通用 UI 描述；未来 MaaFW WebUI integration 应以 PI 为 discovery/config contract，以 Tasker callback/task detail 为 execution event contract，不把现有 maa-cli task JSON 当成跨 integration 协议。
- Confirmed (`2026-07-14_1304-investigate-9am-schedule`): MAA 日志模板按 retry 热读取；可解码 TOML 片段级容错，整份损坏时使用 last-known-good/plain fallback。可见日志配置失败不能阻止外部命令或 run 终态收尾。
- Confirmed (`2026-07-14_0244-optimize-log-template-migration`): 可见日志采用通用 `TemplateBlockRuntime`、per-source preprocess state 和声明式 TOML blocks。raw stderr 的 `MaaTaskResultCollector` 仍是任务结果权威，不依赖展示模板。原始 174 个日志文件的覆盖审计保留在该会话。
- Confirmed (`2026-07-13_1541-review-incomplete-session`): `GenericRunManager` 已保持领域无关，终态 durable-first/live-second；process/store/diagnostics 已脱离 `MaaRuntime`。MAA debug cleanup、MaaCore 增量捕捉和 task result 保留在 MAA 领域。
- Confirmed (`2026-07-12_0055-fix-retention-frontend-split`): run-aware retention 以整 run 为 ownership 单元；前端已按 route 和 JSON Forms editor 分块，现有构筑无 >500 kB warning。
- Confirmed (`2026-07-20_0910-reorganize-storage`): writable roots 分为 panel `data/`、integration `runtime/`、download `cache/` 和独立 ADB credentials；面板持久引用使用 `data:`、`runtime:`、`cache:`，下载 manifest 在自身边界使用 `downloads:`。

## Next feature handoff

- Confirmed (`2026-07-14_0145-audit-gui-tools`): 用户下一轮 tools 范围为“公招识别 + 牛杂”，排除干员识别、仓库识别、牛牛抽卡和牛牛监控。完整上游调用链、参数、五个 Custom 入口、副作用、Recruit callback 缺口与动态限时条目探索保留在该会话 `session.md`。
- Confirmed: Recruit calc-only 使用 `times=0, confirm=[-1]`，不会最终确认招募，但可能设置时间并点击 Tags；当前 maa-cli 丢失 GUI 所需的组合/候选干员明细，实施完整结果页前必须建立 MAA 领域结构化 result 边界。
- Confirmed: 四个商店类 Custom 工具会真实消费资源，不能无条件继承通用 1–50 retry 控件；UI/descriptor 必须声明副作用和 retry policy。
- Unknown: 首轮是否同时实现 Maa API 动态下发的限时 miniGame 条目；若会改变 registry/descriptor 结构，应先确认产品范围。

## Environment and deployment

- Confirmed (`2026-07-21_1125-check-ad3-stage-support`): 框架自有推荐缓存代码尚未部署到正在运行的 systemd 进程；检查时 manual run `f2aa03f4f842` 正在真实作战，因此没有重启或干预。任务自然结束后需安全重启 `maa-auto-panel-webui.service`。
- Confirmed (`2026-07-20_0910-reorganize-storage`): 部署前四类 manager 均无 active run。已停服并清除旧 diagnostics/history、根 `debug/`、generated configs 与 MAA native debug，保留 `data/config`、scheduler stats/trigger、cache 和 MAA 安装；`maa-auto-panel-webui.service` 已重启并运行新代码。
- Confirmed (`2026-07-20_0910-reorganize-storage`): 部署 smoke：`GET /api/runs/history` 返回空列表，旧 API 404；新目录树符合契约；`maa version` 在新 cwd 成功返回 maa-cli 0.7.5 / MaaCore 6.14.2。此次只运行非设备操作。
- Confirmed: 开发/裸机 systemd 与未来 Compose 实例不得同时连接同一设备或共享 data/cache/ADB state；当前框架/协调/store 仍是单进程模型。
- Confirmed: 产品威胁模型仍为可信内网、单用户；不因本轮审计引入认证、RBAC、数据库、微服务或动态第三方 Python 插件。
- Confirmed (`2026-07-11_0111-audit-container-plan`): 隔离容器安装曾发现官方 stable runtime 的 OpenCV SONAME 混合风险；`maa version` 不能替代真实设备 plugin smoke。原始容器探索会话继续保留。
