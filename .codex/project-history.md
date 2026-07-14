# Project History

面向无上下文后续会话的当前项目交接。仅记录仍有效的事实、风险和方向。
置信度：Confirmed / Likely / Hypothesis / Unknown。

## Current repository

- Confirmed (`2026-07-10_0004-complete-rename-maa-auto-panel`): 项目名 `Maa Auto Panel`；Python 包 `maa_auto_panel`；distribution/CLI slug `maa-auto-panel`；入口 `maa-auto-panel = maa_auto_panel.cli:main`。仓库 `/root/Maa_auto_panel`，远端 `Starseeker-xz/Maa_auto_panel`。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): 当前通用框架目录为 `data/config/framework`、`data/state/framework`、`data/debug/framework`、`data/history/framework`；MAA 安装已从 data 拆为独立 `runtime/maa`；download cache 为 `cache/downloads`。任务 metadata namespace 为 `framework`；runtime placeholder 为 `__framework_runtime__:*`；schema 扩展键为 `x-frameworkManaged`。
- Confirmed (`2026-07-10_0416-full-project-audit`): 2026-07-10 工作区含尚未提交的大规模重命名/通用化改动。后续操作必须保留这些用户改动，不得按 HEAD 旧路径判断当前架构。
- Confirmed (`2026-07-11_1805-consolidate-audits`): 根目录审计已统一为 `BACKEND_AUDIT.md` 与 `FRONTEND_AUDIT.md`；后续审计只修改这两份。改代码时可酌情参考，但必须先核对当前实现，因为报告结论大概率会过时。原 `PROJECT_AUDIT.md`、`PATH_MANAGEMENT_AUDIT.md`、`CONTAINERIZATION_PLAN.md` 已被整理替代。

## Product direction

- Confirmed (`2026-07-11_0111-audit-container-plan`): 容器文件当前用于固化未来部署边界，不代表立即生产切换。未经用户明确要求不得 build/up Docker；日常开发继续使用现有 systemd 服务重启。当前 dev/systemd 与 Docker 实例绝不并行连接同一 redroid 或共享 data；若未来需要并行开发，必须隔离设备、data/cache/ADB state 并禁用开发 scheduler。
- Confirmed (`2026-07-10_0416-full-project-audit`): 当前功能闭环已基本完成，主要工作转为架构重整、长期运行可靠性与通用扩展。
- Confirmed (`2026-07-10_0416-full-project-audit`): 目标是让 MAA/maa-cli 成为自动化框架的一个 integration，并支持未来其他 maa-cli 类工具及正式自定义脚本接口。
- Confirmed (`2026-07-10_0416-full-project-audit`): 当前不需要数据库、微服务或动态第三方插件加载器。优先顺序是运行/安全基线 → 框架上下文解耦 → 内部 Action/Integration registry → 第二 integration 验证。
- Confirmed (`2026-07-13_1500-audit-run-architecture`): 用户明确 `GenericRunManager` 不得包含任何运行分类的专项语义。MAACore log capture、MAA installation cleanup 等必须留在 `maa/` 领域 callbacks/协作者中，不能注入或泄漏到通用 manager；manager 只观察 opaque plan/command/result/artifact 数据。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): 容器化目标为单 panel 容器、外部 TCP redroid、普通 bridge 网络、非 privileged、单实例；框架 `data`、integration `runtime`、download cache、ADB credential 使用四个独立持久化边界；`runtime/maa` 与框架 data 和应用镜像版本解耦。
- Confirmed (`2026-07-10_0416-full-project-audit`): 用户明确产品威胁模型为“可信内网、单用户”，不需要为公网/多租户假设引入登录、token、session、RBAC、用户数据库或认证反代。网络边界由 LAN/防火墙和 Compose publish 地址承担；若产品前提未来改变再单独评估认证。

## Current architecture

- Confirmed (`2026-07-14_0244-optimize-log-template-migration`): MAA 可见日志已完成 block-runtime 迁移。通用 `TemplateBlockRuntime` 从严格 TOML 自动注册 block、匹配/reprocess start/end、翻译与 fallback、追加有界 record、派生状态和关闭策略；模板不使用人工 rule/event id。`maa/log_templates.py` 从 510 行降至 141 行，不再手工构造 `BlockDefinition`。
- Confirmed (`2026-07-14_0244-optimize-log-template-migration`): `LogSourceSpec` 支持每 source 有状态 raw-line preprocessor；`LogLineInput` 同时保留原始 raw 与处理后 content/metadata。MAA 预处理器只负责移除 maa-cli envelope、提取 time/level/tone，并在检测到 OperBox/Depot pretty JSON 后持续静默到对象闭合；状态属于单个 buffer/source，不跨 retry/run，共享 diagnostics/raw-result 仍保留原文。
- Confirmed (`2026-07-14_0244-optimize-log-template-migration`): `RunLogProfile` 直接携带 `source_specs`，运行注册处声明可见 source；`configure_buffer` 只初始化每 buffer 独立的模板 runtime/字段监视器。通用 manager 不含 MAA 分支。
- Confirmed (`2026-07-14_0244-optimize-log-template-migration`): MAA 专用可见日志状态只剩按 source FIFO 填充模板无法推断的 `task.id/name/source_name`。任务成功判定仍由独立 `MaaTaskResultCollector` 消费 raw stderr，不受展示模板或 JSON 静默影响。
- Confirmed (`2026-07-14_0244-optimize-log-template-migration`): 对 88 stderr + 86 stdout、共 7,866 行 raw 留存审计后，已删除 summary catch-all、无冒号 RecruitResult、无 index EnterFacility、空 total drops 及 summary Error/Warning 旧规则；未知行统一走保留 raw 的通用 fallback。完整后端 133 passed，174 个 raw 文件 replay 无异常；未重启服务。

- Confirmed (`2026-07-14_0145-audit-gui-tools`): MAA GUI 的公招识别、干员识别、仓库识别分别调用 MaaCore `Recruit`（calc-only 参数 `times=0, confirm=[-1]`）、`OperBox`、`Depot`。公招 calc-only 不确认招募，但会按 GUI 选项设置时长并点击 Tags；OperBox/Depot 会自动尝试导航并逐页横向识别，结果由 `SubTaskExtraInfo` callback 返回并由 GUI 单独持久化。
- Confirmed (`2026-07-14_0145-audit-gui-tools`): GUI“牛杂”不是独立 Core 类型，而是 `Custom.task_names` 选择器。五个常驻入口为 `SS@Store@Begin`、`GreenTicket@Store@Begin`、`YellowTicket@Store@Begin`、`RA@Store@Begin`、`MiniGame@SecretFront@Begin@Ending{A-E}[@事件名]`；另从缓存/在线 `StageActivityV2.json` 动态插入当前开放限时入口。前四项会真实购买，不能当作无副作用识别工具。
- Confirmed (`2026-07-14_0145-audit-gui-tools`): maa-cli v0.7.5 支持 `Recruit`/`Depot`/`OperBox`/`Custom`，但 callback 日志不是统一结构化产品结果：Depot/OperBox 输出完整 pretty JSON，Recruit 只输出最高星级与原始五 Tags，丢弃 WPF 结果页使用的组合及候选干员数组。面板复刻 GUI 结果页前应先建立 MAA 领域结构化 callback/result 边界，不能只依赖当前 visible-log 文本。
- Confirmed (`2026-07-14_0145-audit-gui-tools`): 用户明确后续 GUI tools 范围排除牛牛抽卡（真实消费风险）和牛牛监控（已在别处实现）。上游 WPF 的识别数据由 GUI 进程写入安装目录 `data/OperBoxData.json`、`data/DepotData.json`，Core 不持久化；面板实现应由后端领域状态保存并通过 API 下发，不能依赖浏览器 localStorage。OperBox 只需持久化 own_opers+syncTime，未拥有列表和潜能映射可派生；Depot 持久化 itemId→count+syncTime。

## Next tools implementation handoff

来源会话：`2026-07-14_0145-audit-gui-tools`。本节是下一会话实施“公招识别 + 牛杂”时的权威上游行为记录。

### Confirmed scope

- Confirmed: 用户最终将下一轮范围收敛为公招识别和牛杂功能；不实施干员识别、仓库识别、牛牛抽卡或牛牛监控。
- Confirmed: 这些功能仍应在面板 `tools` 中作为并列工具展示；“牛杂”只是上游 WPF 的分组名，不应在面板领域模型中创建一种 `牛杂`/`MiniGame` Core task type。

### Public recruitment recognition

- Confirmed: 使用 maa-cli/Core 正式任务类型 `Recruit`。WPF 精确构造：`times=0`、`confirm=[-1]`、`select` 为用户勾选的 3/4/5/6 星列表、`set_time` 为“自动设置时间”、`recruitment_time.3/.4` 为用户时间、`.5/.6=540`，并传当前 server；其余刷新、加急、汇报等参数保持默认关闭。
- Confirmed: `confirm` 包含 `-1` 是 Core 的 calc-only 开关。用户必须手动停在某个公招槽的 Tags 选择页；Core OCR 五个 Tags、计算所有组合，不点击最终确认招募。但 calc-only 仍会依照 `set_time` 调整招募时长，并依照 `select` 点击推荐 Tags，因此不是无副作用截图识别。
- Confirmed: WPF 默认配置中 3/4/5/6 星选择均为 true、自动设时为 true；3/4 星允许 1:00–9:00、10 分钟粒度，越界时在 1:00 与 9:00 间回绕；5/6 星固定 9:00。面板是否照搬回绕交互可由自身表单规范决定，但提交给 Core 的分钟数需保持 60–540。
- Confirmed: MaaCore `RecruitResult.details` 包含 `tags`（识别到的五 Tags）、`level`（排序后最佳组合的保底星级）和 `result[]`（全部组合；每项含组合 `tags`、保底 `level`、候选 `opers[{id,name,level}]`）。WPF “显示所有可招募组合”直接渲染 `result[]`。
- Confirmed: 当前 maa-cli v0.7.5 虽收到完整 callback，却只读取 `details.level` 和 `details.tags`，日志/summary 均丢弃 `details.result`；提高 `-v` 不会恢复。实施完整 GUI 结果页前必须先补机器可读的完整 Recruit callback/result 边界，不能从当前 `RecruitResult: ★...五Tags` 可见日志推导所有组合。
- Confirmed: 下一轮范围排除了 OperBox，因此公招结果不需要先实现潜能/MAX/NEW 增强；没有持久化干员数据时应只展示 Core 返回的组合与候选干员，不制造潜能状态。

### Common execution shape for mini-game tools

- Confirmed: 所有牛杂入口均通过 maa-cli/Core `Custom` 运行，params 形态为 `{enable: true, task_names: [<exact task name>]}`，每次只传一个入口。它们使用普通 profile/device 连接及相同 ADB 资源锁；面板应复用 MAA 领域的临时 task config、环境、日志、MAACore diagnostics、结果判断和 cleanup，而不是把 MAA 专项逻辑塞进 `GenericRunManager`。
- Confirmed: 四个商店任务会真实消费游戏货币并购买商品。UI 必须清楚显示前置页面与购买策略；自动 retry 会再次进入消费流程，下一轮需显式决定禁用 retry 或对各任务证明幂等后再开放，不能无条件继承当前工具页 1–50 次重试控件。

### Permanent mini-game entries

- Confirmed: 活动商店兑换入口为 `SS@Store@Begin`。必须在当期活动商店页开始；任务检测可购买商品，选择最大数量并付款、处理新干员/时装获得动画，购买后继续扫描并向右滑动（最多 10 次），资金不足或遍历完成停止；通过无限池检测节点跳过无限池。
- Confirmed: 绿票商店入口为 `GreenTicket@Store@Begin`。可从常规主界面尝试进入商店→凭证交易所→资质凭证区；一层依次识别并最大数量购买寻访凭证、合成玉、龙门币、家具零件、招聘许可、战斗记录、赤金，然后进入二层，仅购买寻访凭证和招聘许可，买不到或目标耗尽后停止。
- Confirmed: 黄票商店入口为 `YellowTicket@Store@Begin`。可尝试进入凭证交易所→高级凭证区并滑动查找，只购买单抽寻访凭证和十连寻访凭证，每次购买后继续扫描直至目标耗尽/无法购买。WPF 唯一前置提示为“请确保至少有 258 张黄票”。
- Confirmed: 生息演算商店入口为 `RA@Store@Begin`。WPF 要求在生息演算活动商店页开始；任务识别商品、选择最大数量、付款、处理获得动画并横向遍历，资金不足或遍历完成停止。
- Confirmed: 隐秘战线向 `Custom` 传动态名 `MiniGame@SecretFront@Begin@Ending{A|B|C|D|E}`，可选再追加 `@支援作战平台`、`@游侠` 或 `@诡影迷踪`。`CustomTask` 解析动态名、设置结局/优先事件、注册 `SecretFrontTaskPlugin`，实际执行资源入口 `MiniGame@SecretFront@Begin`。默认结局为 E。
- Confirmed: 隐秘战线必须在选小队页开始；若有存档须先手动删除，首次教程须手动完成/关闭，上游建议勾选“继承上一支队伍发回的数据”。插件按结局自动选分队：A/B 物资、C 情报、D/E 医疗；固定路线分别为 A=`1A→2A→3A→4A`、B=`1A→2A→3A→4B`、C=`1A→2A→3B→4C`、D=`1A→2B→3C→4D`、E=`1A→2B→3C→4E`。
- Confirmed: 隐秘战线在普通行动卡上 OCR 当前物资/情报/医疗与最多三页卡牌收益和成功率，按距当前阶段/最终结局目标的缺口加权，使用 `收益 × 成功率²` 评分并选择全局最高项；事件页 OCR `1A/2B/...` 并选择目标路线内卡片，否则兜底第一张。配置了优先事件时会先在当前页找该事件；命中后只在当前页做数值选择。流程持续推进、处理危机/结果/重开，直至结局完成节点停止。

### Dynamic entries and unresolved product choice

- Confirmed: WPF 还从 Maa API 缓存 `gui/StageActivityV2.json` 的当前 client（Bilibili 映射 Official）读取 `miniGame` 数组，仅把 UTC 时间窗内 `BeingOpen` 的条目插到常驻项之前；条目携带 Display/DisplayKey、Value（直接作为 Custom task name）、Tip/TipKey、MinimumRequired 和时间窗。截图对应时刻 CN 条目已过期，故只有五个常驻项。
- Unknown: 用户所说“牛杂里的功能”是否要求下一轮同时实现这种随 Maa API 动态变化的限时工具注册，还是先只实现截图中的五个常驻入口。下一会话应在审计现有 Maa API/cache 边界后做最小风险判断；若会明显改变 registry/API 结构，再向用户确认。

- Confirmed (`2026-07-14_0244-optimize-log-template-migration`): active block 的 message/line 统一经 pipeline `append_active_record()` 追加并即时执行 record 上限；模板 runtime 不直接操作 entry 列表。
- Confirmed (`2026-07-14_0244-optimize-log-template-migration`): 未消费的 `RunLogBuffer.output`、`max_output_chunks`、callback 字符串返回及 terminal 文本节流状态已删除；pipeline append/flush 只返回 `state_generation` 是否变化。raw stderr → `MaaTaskResultCollector` 权威结果分支未改变。
- Confirmed (`2026-07-14_0244-optimize-log-template-migration`): 原 1,195 行 `logs/templates.py` 已改为 `logs/templates/` 子包，依赖方向为纯 `model.py`（160 行）→ `engine.py`（294 行）/`loader.py`（429 行）→ `runtime.py`（327 行）；调用方直接导入定义模块，`__init__.py` 不提供大规模 re-export。
- Confirmed (`2026-07-14_0004-optimize-maa-log-format`): 可见日志消息支持可选整数 `indent`，前端每级按 `3ch` 呈现；MAA 翻译器直接为作战掉落/汇报结果、设施产物/换班干员和运行摘要详情标记一级缩进，不维护段落父子关系。富文本片段未指定 tone 时使用默认文字色，不再继承整行 tone；设施名、公招动作、理智数值及摘要序号/合计标签按模板局部强调。
- Confirmed (`2026-07-14_0004-optimize-maa-log-format`): 运行摘要子任务标题中的状态词继续保留语义颜色（完成 success、失败 danger、停止/未知 warning），但不加粗；任务名和耗时使用普通文字。不要把“减少强调”误解为删除状态色。
- Confirmed (`2026-07-14_0004-optimize-maa-log-format`): 连续的企鹅物流/一图流成功汇报日志在同一任务块内折叠为一条“汇报成功”，隐藏平台名和上传 URL；遇到非汇报行后开始新的汇报组。
- Confirmed (`2026-07-14_0004-optimize-maa-log-format`): 状态色修正前确认 current run 已 succeeded 后再次重启 `maa-auto-panel-webui.service`，当前 MainPID 11038；服务 active，`/api/runs/current` 返回 idle。新的后端翻译与前端构建均已加载；旧 history 不回写结构化翻译/缩进。
- Confirmed (`2026-07-14_0004-optimize-maa-log-format`): 应用户要求，本机历史 Run ID `bbd5616d586c` 的两个 retry 已用当前 MAA 翻译规则定向重建 task/summary messages；只修改该 history JSON，原文件备份在本会话 scratch。API `/api/history/runs/bbd5616d586c` 已回读确认新版汇报折叠、缩进与状态色。

- Confirmed (`2026-07-13_2243-frontend-retry-block`): 前端部署可在旧 Python 进程仍运行时先显示新 retry Accordion，但旧进程不会生成 `summary_messages`。用户 smoke 暴露该版本错配后，确认无 active run，并于 2026-07-13 23:08 UTC 重启 `maa-auto-panel-webui.service`；新 MainPID 6379，服务 active/idle。重启前生成的历史不回填摘要，后续新 run 使用完整新链路。
- Confirmed (`2026-07-13_2243-frontend-retry-block`): retry 日志在 `max_retries > 1` 时使用 Radix 单选 Accordion；首次进入/切换历史默认展开最后一项，新 retry 追加时展开新项，普通 SSE、状态变化与 retry 完成均不改变选择。`max_retries = 1` 直接渲染原日志。展开内容无 retry 外框，摘要留在可折叠标题区域。
- Confirmed (`2026-07-13_2243-frontend-retry-block`): `RetryDecision.retry_summary_messages` 通过 `LiveRetry.summary_messages` 进入 SSE、retry index 和完整历史。MAA 手动/定时运行按整次 run 的初始任务清单生成 retry 结果摘要；本 retry 成功/失败/停止/未完成用勾叉和 tone 表示，未执行任务淡化。通用 retry-start 占位事件已清除，避免与 retry 标题重复。
- Confirmed (`2026-07-13_2243-frontend-retry-block`): retry 任务摘要最终符号为成功 `✔️`（U+2714 U+FE0F）、失败 `❌`、停止/未完成 `⚠️`（U+26A0 U+FE0F）。摘要同时接收完整 run 任务、当前 retry 计划任务和 retry 终态：停止发生在 Start 前时，当前 retry 计划内任务显示 `⚠️`；不属于当前 retry 计划且未执行的任务才淡化。码点有测试锁定。
- Confirmed (`2026-07-12_0125-toolbar-scrcpy-notifications`): Toolbar 高度已收紧，设备工具与通知之间增加竖线；共享 `FocusDeleteButton` 使用 accent hover/focus 背景。通知 Sheet 打开时聚焦容器而非首条删除按钮，避免 Radix 自动聚焦导致无 hover 时误显示。独立项目 scrcpy-tool 拥有的通用 URL 协议草案位于 `docs/scrcpy-url-protocol.md`，入口为 `scrcpy-tool://launch/v1`；Maa Auto Panel 仅为调用方。
- Confirmed (`2026-07-12_0125-toolbar-scrcpy-notifications`): Toolbar Scrcpy 入口已接通 `scrcpy-tool://launch/v1`。普通页面点击时即时读取 default profile 的连接地址；定时详情页由 SchedulePage 上送当前 draft profile 地址，因此未保存地址修改也生效。通用 Scrcpy 设置保存于 `framework.scrcpy`，默认视频码率 100 Mbps、最大帧率 60，并生成官方参数 `--video-bit-rate=<n>M`、`--max-fps=<n>`。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): 全局通知子系统位于 `notifications/`，固定五类 tag：runtime 缺失、runtime 更新、手动 MAA 完成、自动定时 MAA 完成、手动触发定时 MAA 完成。成功/失败使用 severity/status 区分，用户停止不通知；Toast 走独立 `/api/notifications/events` SSE，外部发送保留 `ExternalNotificationSender` protocol + 空实现。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): 通知策略独立保存于 `data/config/framework/notifications.toml`，每个 tag 可配置 `toast`/`external`。runtime 缺失在服务启动检查，更新可用复用 maintenance update-info 结果，MAA run 通知由 `GenericRunManager` 持久化终态后的 listener 统一触发。事件缓存有界且持续条件按组件集合去重。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): 前端 App 根挂载 `NotificationCenter`；Settings 的 panel 组件开始收敛到 `frontend/src/pages/settings/panels.tsx`，当前设备配置与通知配置已从页面编排中拆出。通知展示位置与离线语义以后续 `2026-07-11_1805-consolidate-audits` 结论为准。
- Confirmed (`2026-07-11_1805-consolidate-audits`): 通知历史与 Toast 已分离。所有事件进入后端 100 条有界栈，SSE 标记 replay/live；前端右上角铃铛打开 18rem 通知抽屉，所有未读可见、重要未读红点，已读/逐条删除/清空按 event id 保存在当前浏览器。在线事件按 toast policy 弹出；离线成功只入栈，离线失败/警告上线补弹，runtime 缺失/更新可用可显式补弹。
- Confirmed (`2026-07-11_1805-consolidate-audits`): 2026-07-11 smoke 通知曾表现为“能入栈但不 Toast/不显示未读”，根因是 systemd 后端自 03:06 未重启，旧事件缺少新版 `delivery/important/replay_toast` 字段而前端已更新。确认无 active run 后已重启 `maa-auto-panel-webui.service`，新 PID 9847，API 与静态 bundle 为新版，服务 active。
- Confirmed (`2026-07-11_1805-consolidate-audits`): 前端新增贴合右上角、仅左/下边框的 App Toolbar，含通知及 disabled 的 Scrcpy/设备截图预留按钮。通知 Toast 使用 Sonner，抽屉使用 shadcn Sheet（22.5rem），均覆盖 Toolbar；新增共享 `SegmentedControl` 与 `FocusDeleteButton` 并迁移设置/任务/定时相关页面。依赖新增 `sonner` 与 shadcn CLI 引入的 `radix-ui`。
- Confirmed (`2026-07-11_1805-consolidate-audits`): 设置 UI 已分为 `/settings` 基础设置（设备/更新）、`/settings/framework`（框架/通知）、`/settings/theme`。主题只使用前端 localStorage，不再由 framework settings 默认值、API payload 或 App 启动回读后端；后端写设置时删除遗留 theme key。
- Confirmed (`2026-07-11_1805-consolidate-audits`): maintenance 从 running/stopping 进入终态后，设置页自动重新请求 update-info，避免更新成功后继续显示旧的“可更新”。2026-07-11 core-update `0ff39d6eb688` raw 输出仅有 MaaResource fetch，但 `scripts/maa-env maa version` 确认 MaaCore v6.14.1，用户确认 smoke 任务可运行。
- Confirmed (`2026-07-09_1512-run-manager-generalize`): 手动、定时、工具、维护运行统一使用 `GenericRunManager` 与 `LiveRun`/`LiveRetry`；通用 payload 为基础字段 + `metadata` + `artifacts`，live/history 均为 `{run, retries}`。
- Confirmed (`2026-07-13_1500-audit-run-architecture`): 通用 run contracts 已移至 `run_manager/contracts.py`；`CommandSpec` 显式携带 cwd/env，process executor 与 `GenericRunManager` 均不依赖 `MaaRuntime`。manager 继续唯一拥有 live state、锁/condition、retry loop、资源申请时序和 stop/finalize；源码无 MAA/manual/schedule/maintenance/tool 分类分支。thread 在 run 可见前已启动，stop/force-stop diagnostics 文件 I/O 已移到 manager 锁外。
- Confirmed (`2026-07-13_1500-audit-run-architecture`): `RunStateStore` 与 `Diagnostics` 现仅依赖 `FrameworkPaths + PathReferenceResolver`。Diagnostics 新增通用 raw-byte `capture_file_increment(source, start_offset, capture_id)`，返回 logical log reference、next offset、captured bytes；MAA manual/schedule callbacks 每个实际执行 retry 自行提供 MaaCore source/offset 并捕捉一次，通用 artifact role 为 `diagnostic_log_file`。
- Confirmed (`2026-07-13_1541-review-incomplete-session`): Diagnostics 的 maa-cli/tool/script 重复 API 已完整收敛为 channel-based `stream_log_files`/`stream_sink`；通用层不内建运行分类。MAA debug retention 位于新 `maa/cleanup.py`，只依赖 `MaaInstallation`，在启动和实际 MAA attempt 后执行。
- Confirmed (`2026-07-13_1541-review-incomplete-session`): run 终态改为 durable-first/live-second，持久化有限重试；成功提交后才发布 live 终态，post-finish retention/listener 与核心提交隔离，持续持久化失败 fail-closed 并由启动恢复流程收尾。
- Confirmed (`2026-07-13_1500-audit-run-architecture`, completed by `2026-07-13_1541-review-incomplete-session`): 五类应用异常与 FastAPI handlers 已实施，原 routes/shared run router 的 39 处 builtin→400/404/409 映射已清除；config validation 保留 422。durable JSON、config、schedule 与 task corruption 边界已补齐；上一会话漏改的 channel retention 测试已完成，当前完整后端为 119 passed。
- Confirmed (`2026-07-06_0037-callback-run-manager`): manager 拥有 command/retry/lifecycle；领域只通过 callbacks 决定动态命令、raw-line 消费、attempt 结果和是否继续。不要恢复 driver-owned retry loop。
- Confirmed (`2026-07-10_0416-full-project-audit`): `RunCoordinator` 跨四类 manager 共享，当前主要仲裁相同 ADB address；schedule auto > schedule manual > normal。
- Confirmed (`2026-07-10_0416-full-project-audit`): 状态、history、diagnostics、framework logging 分离。保持该分离；scheduler daily stats/trigger state 继续留在 scheduler domain。
- Confirmed (`2026-07-10_0416-full-project-audit`): 当前“通用层”仍接收 `MaaRuntime`。应拆成 `FrameworkPaths`、`ProcessContext`、`MaaInstallation`，使 process/run manager/store/diagnostics 不再依赖 `maa.*`。
- Confirmed (`2026-07-10_1752-audit-data-paths`): 已新增 `ApplicationPaths`、`FrameworkPaths`、`CachePaths`、`MaaInstallation`、`PathLayout`；`MaaRuntime` 是组合这些路径的 runtime aggregate。路径所有权已拆开，但 process/run manager/store/diagnostics 的类型依赖仍可在后续进一步收窄。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): `FrameworkPaths` 不再包含 runtime；新增 `MAA_AUTO_PANEL_RUNTIME_DIR`/`--runtime-dir`，`MaaInstallation` 从独立 runtime root 派生。容器对应 `/app/runtime` 和 `MAA_PANEL_RUNTIME_PATH` bind mount。本机已一次性迁移为 `runtime/maa`，systemd 恢复 active，API idle 与 `maa version` 验证通过。
- Confirmed (`2026-07-11_2113-fix-persistent-paths`): 持久路径统一采用带逻辑根的字符串引用：`framework:...`、`runtime:...`、`downloads:...`。`PathReferenceResolver` 集中负责生成、重定位解析与路径逃逸校验；history/diagnostics/trash/MAA artifact/download manifest 不再依赖 repo root 或宿主绝对部署位置。项目未发布，不保留旧引用格式兼容层。
- Confirmed (`2026-07-11_2105-audit-stream-no-newline`): 统一进程执行器已改为 non-blocking binary read + 每流 UTF-8 incremental decoder/有界分行。任意 bytes 会刷新静默计时，完整输出仍按旧逻辑行边界进入 diagnostics/可见日志/raw callback；partial-output timeout、stop escalation、跨 chunk UTF-8 与 CR/LF/EOF 分块测试通过。
- Confirmed (`2026-07-12_0055-fix-retention-frontend-split`): run retention 已以 run ownership 闭环：终态释放 plan/callback，manager 仅保留 active 或最近终态 snapshot；run/retry 联合上限按整 run 淘汰，先原子移除索引再级联 history、diagnostics 与白名单 owned artifacts，未知/shared artifact 保留。手动删除同步 manager，active delete 返回 409。
- Confirmed (`2026-07-12_0055-fix-retention-frontend-split`): 前端已按 route lazy 分离 Main/Schedule/Tools/Settings/Theme，并仅在选中 task item 时 lazy 加载 JSON Forms editor；共享 LazyBoundary 处理 fallback/chunk error。构筑入口 413.62 kB gzip 132.00 kB，editor 289.90 kB gzip 94.29 kB，各 route 1.58–27.37 kB，不再有 >500 kB warning。
- Confirmed (`2026-07-12_0055-fix-retention-frontend-split`): ConfirmDialog 已迁移 Radix AlertDialog；设置分类为 NavLink，配置/定时同页切换为 Radix Tabs，旧 SegmentedControl 删除；三类列表的 rename 生命周期复用 `useInlineRename`，Toolbar 图标说明复用 Tooltip。浏览器 smoke 验证 route chunk、非编辑器首屏不加载 editor、Escape dialog 与方向键 Tabs。
- Confirmed (`2026-07-10_2207-graceful-shutdown`): FastAPI lifespan 现在拥有 scheduler/WebServices 生命周期。SIGTERM 先结束 SSE，再停止 scheduler、关闭 coordinator、并行通知四类 manager；正常/强停共享 60s/15s absolute deadline，最后 flush diagnostics 和 join 非 daemon 线程。
- Confirmed (`2026-07-10_2207-graceful-shutdown`): 所有外部 command 使用独立 POSIX session；stop/force-stop 分别向完整 process group 发送 SIGTERM/SIGKILL，测试确认 SIGTERM-ignoring descendant 会被清理。
- Confirmed (`2026-07-10_0416-full-project-audit`): 自定义脚本当前只有 schedule restart hook；工具 registry 仅在 `ToolRunManager` 中硬编码 `game-update`。未来以本地可信 manifest + ActionSpec 扩展，不应先开放 Web 任意脚本上传。

## Active high-priority findings

- Confirmed (`2026-07-11_0111-audit-container-plan`): WebUI 手动更新后宿主 `maa version` 可报告 maa-cli 0.7.5 / MaaCore 6.14.0，但官方 stable 安装脚本 + 全新容器卷 `maa install --batch stable` 仍产生混合 Linux runtime：core 依赖 OpenCV `.411`，ADB control plugin 依赖 `.412`，artifact 仅含 `.411`。`maa version` 未加载 ADB plugin，不能作为设备任务可用证明。基础应用镜像不受阻；真实设备 smoke 暂缓，禁止伪造 SONAME symlink。
- Confirmed (`2026-07-10_0416-full-project-audit`): 服务以 root 身份监听 `0.0.0.0:8000` 是裸机测试方式；在可信内网单用户前提下，无 authentication scheme 不视为缺陷。容器仍应避免 privileged/Docker socket/host network，并用低成本专用 UID/capability 收缩宿主影响面。
- Confirmed (`2026-07-10_0416-full-project-audit`): 上述 root/监听状态是裸机测试方式，不能原样判定为目标容器缺陷。容器实施时重新以 UID/capability/volume/published port 评估；TCP ADB 不需要 privileged、host network 或宿主 USB mount。
- Confirmed (`2026-07-11_1805-consolidate-audits`): runtime 资源模型已支持 shared/exclusive claim。手动与定时 MAA run 通过统一 helper 声明共享 `integration-runtime:maa` + 独占 ADB device；core/resource/cli maintenance update 声明独占且不可抢占的 runtime lease。相同资源仅在至少一方 exclusive 时冲突，不会串行化不同设备上的 MAA run，也不会让高优先级 schedule 中途停止更新。
- Confirmed (`2026-07-11_2105-audit-stream-no-newline`): 无换行 reader P0 已修复。修复前 runtime kill=1s 的 partial-line child 会运行 3.01s 后自然退出且未标记 timeout；修复后按阈值终止，并保持既有日志逻辑行分块。
- Confirmed (`2026-07-10_2207-graceful-shutdown`): lifespan/shutdown/process-group P1 已修复。真实 systemd + SSE 验收为 586ms、`inactive/success`、`ExecMainStatus=0`；live unit `TimeoutStopSec=120`，服务随后恢复 active/idle。
- Confirmed (`2026-07-11_1805-consolidate-audits`): 资源申请已纳入完整 run 生命周期。`start()` 先建档/接通日志与 SSE 并返回，worker 完成 on_start/before_run 后申请资源；拒绝/超时形成带 event 的 failed run 且不启动 command，同优先级等待以 live event + 持久化 `metadata.resource_wait` 报告。全局 `framework.run_resources.wait_timeout_seconds`（默认 300s）统一限制等待，stop/shutdown 可唤醒。retry 作为 attempt/log 容器，冲突会有 1 个 failed retry 但无实际进程执行。
- Confirmed (`2026-07-12_0055-fix-retention-frontend-split`): manager 内存与 history retention P1 已修复；淘汰/手动删除以整 run ownership 单元级联，diagnostics orphan cleanup 会保护仍被 retained run 引用的路径。
- Confirmed (`2026-07-10_0416-full-project-audit`): active retry 只在 seal 时持久化；崩溃恢复会丢失当前 retry 的结构化可见日志。建议节流 checkpoint。
- Confirmed (`2026-07-10_0416-full-project-audit`): game updater 只校验 HTTP/Content-Length/versionCode，没有 APK hash、package identity 或 signing certificate 验证。

## Other active issues

- Confirmed (`2026-07-02_2144-manual-stop-delay`): MaaCore 冷 ADB server 路径曾出现约 60 秒 `adb devices` 延迟。保持本地 adb server、`kill_adb_on_exit=false` 可规避；详细复现仍保留为活跃会话。
- Confirmed (`2026-06-30_2318-gpu-ocr-research`): 当时的 MaaCore build 只有 CPU ONNX Runtime provider。升级 MaaCore 后需重新验证 GPU OCR，旧会话已归档。
- Confirmed (`2026-07-10_1752-audit-data-paths`): `.venv/bin/maa-auto-panel` shebang 已指向当前 `/root/Maa_auto_panel/.venv/bin/python3`，systemd 的 `uv run maa-auto-panel` 可重启；当前环境没有 Ruff executable/module，pytest 使用 `.venv/bin/python -m pytest`。
- Confirmed (`2026-07-12_0055-fix-retention-frontend-split`): 前端仍无正式自动测试套件；route/editor lazy 与组件语义已有一次性 Playwright smoke，但 SSE reconnect、editor managed metadata、schedule 状态和通知恢复仍应补正式测试。
- Confirmed (`2026-07-10_0416-full-project-audit`): 当前 lock 中 `idna`、`lxml`、`requests`、`soupsieve`、`urllib3` 有 pip-audit 公告；多项实际调用面较低，但 urllib streaming download 更相关。刷新 lock 后需跑 game update smoke test。

## Verification baseline

- Confirmed (`2026-07-13_2243-frontend-retry-block`): retry Accordion/摘要实施后，`.venv/bin/python -m pytest -q` 为 120 passed，compileall、frontend `npm run build` 与 `git diff --check` 通过。独立 Playwright fixture 验证首次/历史最后一项、新 retry 自动展开、普通更新与完成不改展开、手动单选/收起、键盘操作、单次运行无 wrapper 和折叠摘要；测试 Vite 服务已停止，未重启 systemd 服务。
- Confirmed (`2026-07-13_1541-review-incomplete-session`): 完成上一会话收尾修复后，`.venv/bin/python -m pytest -q` 为 119 passed；compileall 与 `git diff --check` 通过。未启动或重启服务。
- Confirmed (`2026-07-11_0111-audit-container-plan`): 基础容器文件已实现并构建 `maa-auto-panel:local`（context 1.80 MB，image 325 MB，UID/GID 10001）。最终镜像 CLI/import/frontend/schema/adb/git/curl 通过；隔离临时卷 Web 首页与 SIGTERM exit 0 通过；测试后 systemd 恢复 active，未启动常驻 panel 容器。
- Confirmed (`2026-07-10_0416-full-project-audit`): Ruff passed；compileall passed；`.venv/bin/python -m pytest -q` 为 66 passed；Vulture 无发现；frontend build passed；`npm audit` 0 vulnerabilities；`git diff --check` passed。
- Confirmed (`2026-07-10_0416-full-project-audit`): 运行环境审计时 scheduled run 正在执行，未被审计操作中断；systemd unit 为 `maa-auto-panel-webui.service`，disabled 但 active。

## Documentation and state

- Confirmed (`2026-07-10_0416-full-project-audit`): `.codex/conversations/` 只保留当前审计、当前命名状态和仍未解决的 ADB 延迟会话。其余 39 个完成/被覆盖会话统一归档到 `~/.codex/archived_sessions/maa-auto-panel/`。
- Confirmed (`2026-07-10_0416-full-project-audit`): 架构/运行/路径/API 变化时检查 `README.md`、`docs/README.md`、`docs/maa-runtime.md`、`docs/architecture-direction.md` 和本文件。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): 路径布局区分四类所有权：`data_root` 只保存框架拥有的 config/state/history/debug；`runtime_root` 保存 integration 安装与自身 XDG 状态；downloads 是独立可重建 cache；ADB 客户端密钥使用独立 `adb-state` volume。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): `docs/BACKEND_AUDIT.md`、`docs/FRONTEND_AUDIT.md` 是审计专用文档，在进行审计时，应始终只对这两个文件进行修改，在定位已有问题时，可以一定程度上参考其内容，但不应完全信任，因为其大概率已一定程度上过时。
- Confirmed (`2026-07-10_1752-audit-data-paths`): 本机目录已一次性调整到最终 `data/` 与 `cache/downloads/` 布局；服务已恢复 active。config API、历史详情、两个 APK cache path、maa-cli/MaaCore version 均验证通过。项目未发布，不保留迁移 CLI、layout version 或旧布局兼容逻辑。
- Confirmed (`2026-07-11_2105-audit-stream-no-newline`): 本机 68 个 state/history/config/manifest JSON 已在停服后一次性原子改写为逻辑根引用，旧格式扫描为 0；备份位于本会话 scratch。systemd 已恢复 active，历史详情可读取 12 个结构化日志块和 3 个事件，两个 APK manifest 路径可解析。
- Confirmed (`2026-07-10_1752-audit-data-paths`): 即使 `/api/runs/current` 为 idle，systemd stop 仍在 20 秒后 SIGKILL。journal 直接停在 Uvicorn `Waiting for connections to close`，很可能有 WebUI SSE/EventSource 长连接未及时结束；idle 只表示没有 MAA run，不代表没有 HTTP 长连接或后台线程。迁移在 unit 完全停止后才开始。
