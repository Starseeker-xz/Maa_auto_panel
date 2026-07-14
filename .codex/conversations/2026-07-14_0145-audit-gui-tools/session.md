# Session 2026-07-14_0145-audit-gui-tools

## 目标

- 只读审计根目录已有 MAA GUI 上游源码，确认截图中公招识别、干员识别、仓库识别及“牛杂”子工具的实际运行逻辑。
- 为 Maa Auto Panel 后续在 `tools` 中并列实现这些能力提供调用链、参数、前置页面与结果形态依据。

## 当前状态

- 已完成会话启动状态读取和上游源码审计。
- 上游副本：`external/MaaAssistantArknights`，commit `884375e925aec46a4911ca2a5731da9f0c776602`（2026-07-04）；本机 runtime 为 `maa-cli v0.7.5 / MaaCore v6.14.1`。
- 尚未修改功能代码或运行环境，也未触发任何设备/游戏任务。
- 用户要求将下一轮实施范围收敛为“公招识别 + 牛杂”；完整 handoff 已写入 `.codex/project-history.md` 的 `Next tools implementation handoff`，供新 session 启动时直接读取。

## 临时假设

- 用户当前要求是先查明上游逻辑，不实施面板功能。
- 用户明确不加入牛牛抽卡（风险过大）和牛牛监控（已在别处实现）；后续范围排除二者。
- 用户进一步明确不实施干员识别、仓库识别；下一轮只做公招识别和牛杂功能。
- “牛杂”是否包括 Maa API 动态下发的当期限时条目尚未明确；五个常驻入口已经完整确定。

## 审计结论

- 公招识别使用 Core `Recruit`，GUI 参数为 `times=0`、`confirm=[-1]`、`select=[勾选星级]`、`set_time` 和各星级时长。`-1` 使 Core 进入 calc-only：只分析当前手动打开的 Tags 页，不确认招募，但按选项会设置时间并点击 Tags。GUI 依赖原始 `RecruitResult` callback 展示所有组合与候选干员，并用持久化干员识别数据附加潜能。
- 干员识别使用 Core `OperBox` 空参数。Core 尝试从当前页/首页自动进入干员列表，切到职业筛选和等级排序，横向滑动逐页 OCR；过程及完成 callback 含 `own_opers`，GUI 再以本地全干员表计算未拥有列表，保存同步时间和结果。
- 仓库识别使用 Core `Depot` 空参数。Core 尝试从当前页/首页自动进入仓库，切到养成材料页，横向滑动到末尾并持续回调 `{done,data}`；GUI 保存最终 item-id→数量和同步时间。
- 牛牛抽卡使用 Core `Custom`，`task_names=[GachaOnce]` 或 `[GachaTenTimes]`；会真实点击寻访和确认，资源不足时停止。GUI 强制风险确认，并在运行时用高频截图监控展示画面。
- 牛牛监控不是 MaaCore task：GUI 连接设备后按 1–600 FPS 目标反复调用强制截图 API、丢弃旧帧，并在持续跟不上时降低目标 FPS；停止监控时若它自己启动了连接或正在抽卡，会 stop 整个 Maa 任务。
- “牛杂”本身不是任务类型。五个常驻入口均包装成 Core `Custom` 的单个 `task_names`：活动商店 `SS@Store@Begin`、绿票商店 `GreenTicket@Store@Begin`、黄票商店 `YellowTicket@Store@Begin`、生息演算商店 `RA@Store@Begin`、隐秘战线动态名 `MiniGame@SecretFront@Begin@Ending{A-E}[@事件名]`。前四者会真实购买商品；隐秘战线由 `CustomTask` 解析动态名并注册路线插件。
- 牛杂还会从 `StageActivityV2.json` 动态插入当前开放的限时小游戏，只有 `BeingOpen` 的条目显示；常驻五项是 GUI 内置 fallback。截图时 CN/Bilibili 对应限时条目已过期，因此只显示常驻项。
- maa-cli 支持 `Recruit`、`Depot`、`OperBox`、`Custom`，可通过临时 task config 运行。但输出边界不同：Depot/OperBox 会把完整 raw callback pretty JSON 写入日志；Recruit 只输出最高星级和五个原始 Tags，丢弃 GUI 所需的组合/候选干员明细。因此后续若要求复刻 GUI 结果页，不能只依赖当前可见日志解析，需先设计结构化 callback/result 边界。
- WPF GUI 在自身进程中将识别结果持久化到安装目录下 `data/OperBoxData.json` 和 `data/DepotData.json`，不是交给 MaaCore 保存。OperBox 文件只保存 `done`、完整 `own_opers`（含 id/name/elite/level/own/potential/rarity）和 `syncTime`；未拥有列表与 `id -> potential` 映射在加载后从已拥有数据及当前资源全干员表派生。Depot 文件保存 `done`、`data: {itemId: count}` 和 `syncTime`。公招结果本身不持久化，只读取内存中的潜能映射增强展示。

## 精确检查

- 只读查看 WPF ViewModel/XAML、AsstProxy、Core InterfaceTask/RecognitionTask、tasks resources、maa-cli callback/schema、面板现有 ToolRunManager。
- 执行 `scripts/maa-env maa version`，输出 `maa-cli v0.7.5`、`MaaCore v6.14.1`。
- 未运行测试（本轮无功能修改），未连接或操作设备。
