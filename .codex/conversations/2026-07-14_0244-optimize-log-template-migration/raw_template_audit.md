# 子代理审计：原始 MAA stdout/stderr 与模板精简

- 父会话：`2026-07-14_0244-optimize-log-template-migration`
- 子代理：`raw_template_audit`
- 性质：只读审计；未修改生产代码、模板、服务或依赖。

## 样本范围

- 主样本：`data/debug/framework/external/maa-cli/` 下 88 个 stderr 文件、86 个 stdout 文件，共 5,331 行 stderr、2,535 行 stdout，约 952 KiB。
- stderr 内可解析时间跨度：2026-07-04 至 2026-07-14。
- 辅助样本：`.codex/conversations/2026-07-14_0004-optimize-maa-log-format/scratch/bbd5616d586c.before-log-retranslation.json` 与 API readback，用于核对结构化展示结果，不作为规则频次主来源。
- 测试样本：`tests/test_maa_logs.py`、`tests/test_log_templates.py`，仅用于识别哪些零命中规则是测试人为保留的兼容分支。

注意：同一个 raw 文件可能串接多次 attempt；以下数字是“行命中次数”，不是独立 run 数。

## 可直接删除或交给通用 fallback

### 1. 删除 summary 尾部 catch-all

位置：`blocks.summary.rules[18]`，即 `{body:text}`。

- Confirmed：在真实 summary 上下文中仅命中 51 行：43 行 `[...] Unstarted`、8 行 `[...] ... - Unfinished`。
- Confirmed：其 `furni`、`Refreshed`、`Recruited` replacements 在这些命中上均没有作用；有内容的招募行和掉落行已经被前置专用规则捕获。
- 建议：删除整条规则，让通用 runtime fallback 保留原文与 `raw`。summary 的默认一级缩进应是 runtime/block 配置，而不是靠 catch-all 伪造翻译。
- 置信度：高。

### 2. 删除无冒号的 `RecruitResult` 变体

位置：`blocks.task.rules[4]`，`RecruitResult {result:text}`。

- Confirmed：带冒号版本命中 103 次；无冒号版本命中 0 次。
- 建议：只保留 `RecruitResult: {result:text}`；若未来格式变化，先由通用 fallback 显示原文，再依据新 raw 证据补模板。
- 置信度：高（对当前保存的 MAA 版本和配置）。

### 3. 删除无房间编号的 `EnterFacility` 变体

位置：`blocks.task.rules[14]`，`EnterFacility {facility:word}`。

- Confirmed：`EnterFacility {facility} {index}` 命中 920 次；无 index 版本命中 0 次。样本中的 index 均类似 `#0`。
- 建议：删除无 index 版本，未知格式走通用 fallback。
- 置信度：高。

### 4. 删除空 `total drops:` 变体

位置：`blocks.summary.rules[9]`，精确匹配 `total drops:`。

- Confirmed：空版本命中 0 次；带 `{drops}` 版本命中 43 次。
- 建议：删除空版本；即使未来出现，原样 fallback 也不会丢失信息。
- 置信度：高。

### 5. 删除 summary 的 `Error:` / `Warning:` 翻译规则

位置：`blocks.summary.rules[16]` 与 `[17]`。

- Confirmed：stdout summary 上下文均为 0 次。
- Confirmed：语料中的 87 行 `Error: ...` 全在 stderr；其中任务结束由 `{source_name} Error`（210 次）或用户中断（11 次）处理。`Warning:` 为 0 次。
- 建议：删除这两条 summary 规则。stderr 错误应由任务生命周期/普通行 fallback 处理，不应在 summary 模板中保留未发生的跨流假设。
- 置信度：高。

## 零命中，但不建议仅凭本批样本立即删除

以下规则确实为 0 命中，但受运行配置或停止路径影响，不能与明显旧格式等同：

- `blocks.task.rules[9]`：`Use {count} medicine` 为 0；临期药版本命中 5。普通理智药是否出现取决于任务配置。
- `blocks.summary.rules[6]`：使用普通理智药且无 expiring 括号的 Fight 摘要为 0；带 expiring 版本命中 1，无药版本命中 42。
- `blocks.summary.rules[3]` / `[4]`：`Stopped` / `Unknown` 为 0；但这是状态语义，而不是纯展示兼容。
- `blocks.task.end[2]`：`{source_name} Stopped` 为 0；当前人工停止样本表现为 `Error: Interrupted by user!` 11 次。
- 全局精确翻译 `ProductUnknown`、`NotEnoughStaff`、`MissionCompleted`、`MissionFailed` 均为 0。其中 `ProductUnknown` 仍被现有测试显式覆盖，说明它是有意支持的 MAA 事件，不宜只按频次删除。

若项目明确采用“只支持当前实证格式，未来变化一律先 raw fallback”的政策，上述展示翻译可以继续删；但 task end 的 `Stopped` 涉及生命周期状态，删除前应同时确认结果收集器与 UI 的停止语义，而不是单独改模板。

## 应保留的模板声明

- task start 636 次；Completed 413 次；Error 210 次；用户中断 11 次。
- resource stdout start：`Already up to date.` 156 次，`Updating old..new` 5 次。
- fetch stderr start：`From https://github.com/...` 161 次。
- summary start：140 次。
- 两套 lookup 都不是冗余表：9 个 product 值与 8 个 facility 值全部在语料中出现，包括 `OriginStone` 28 次、`Training` 35 次。
- task 主体高频规则均有实证：EnterFacility 920、CustomInfrastRoomOperators 562、ProductOfFacility 530、Current sanity 190、Mission started 93、Drops 88、公招相关 27–103、汇报 noise/success 各 30。
- summary 主体高频规则均有实证：Completed 408、Error 210、设施摘要 484、掉落序号 191、total drops with content 43、公招详情 17–25。

## 适合统一交给通用 runtime 的原样行

- task 内未命中模板的真实行只有 49 行、6 种正文：`BattleFormation ...`、`BattleFormationSelected ...`、三种 `CurrentSteps ...`、`识别错误 HasReturned`。这些不需要 MAA 专用 fallback，通用 fallback 保留正文、raw、预处理得到的 time/level/tone 即可。
- resource/fetch block 的后续 git 输出本来就是 pass-through；模板只需声明 start 边界和 block 展示默认值，不需要逐行 MAA translator。
- summary 的 Unstarted/Unfinished 目前无需 catch-all；通用 block fallback 加默认 indent 即可原样展示。如果未来需要中文化或状态色，再添加明确规则，不应恢复全吞 catch-all。

## 合并建议

- 四条 summary 终态标题（Completed/Error/Stopped/Unknown）结构重复，但当前模板能力不能按捕获到的 status 动态选择 text、tone 和 styles。不要把条件映射退回 MAA Python 层。
- 若通用模板编译器未来增加“捕获值 -> 输出值/样式”的声明式映射，可合并为一条 `[{task}] ... {status:word}`；在此之前保留有实证的 Completed/Error 两条更清晰。零命中的 Stopped/Unknown 是否保留按上面的生命周期政策决定。

## 未来易复发的项目级陷阱

- Confirmed：模板末尾的全匹配规则会把未知格式计为“已匹配”，掩盖规则覆盖缺口；覆盖率审计必须单列 catch-all 命中正文，或直接禁止 block 尾部无语义 catch-all。
- Confirmed：raw 文件会串接多个 attempt，不能把文件数或匹配数当作 run 数。
- Confirmed：stdout/stderr 分文件保存，无法从单文件重建跨流精确先后顺序；跨流关闭策略必须靠 pipeline 事件序列验证，不能仅凭这批离线文本推断。
- Confirmed：history 中 active block 会受有界裁剪影响，缺少 start/end 行；审计格式支持范围应以 `data/debug/framework/external/maa-cli/*.log` 为主，history 只用于验证最终展示。
- Likely：现有单元测试包含没有 raw 实证的兼容变体；删除旧模板规则时要同步判断测试是在保护真实契约还是只在固化旧实现，不能因测试存在就默认规则仍有价值。
