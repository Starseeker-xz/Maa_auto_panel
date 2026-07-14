# Session 2026-07-14_1304-investigate-9am-schedule

## 目标

- 起初只读诊断最近一次本地 09:00 定时运行为何未成功；随后用户授权修正模板、实现运行时热读取/局部容错/基础 fallback，并要求配置异常通过既有 SSE 固定回报但不得阻止运行。

## 已确认事实

- framework effective timezone 为 `Europe/London`；2026-07-14 处于 BST (UTC+1)。`daily-test` 的 `t2200 / 休息 2` 配置时间为 09:00。
- scheduler 在 `2026-07-14T08:00:02+00:00`（09:00:02 BST）正常触发 run `12d74b2400e4`，并已写入 triggered state；不是漏调度。
- run 未创建 maa-cli stdout/stderr，也没有 maa-cli/MaaCore/adb 子进程。唯一 event 为模板验证失败。
- 直接调用 `maa_translation_template()` 可稳定复现 `TemplateValidationError`: `blocks.fetch.start[0].tone: unknown field`。
- 当前未提交 `src/maa_auto_panel/maa/log_template.toml` 在 `blocks.fetch.start[0]` 新增 `tone = "info"`；boundary loader 只允许 `source/match/values/reprocess/message/message_tone`。文件 mtime 为 `2026-07-14 04:41:22 UTC`。
- 04:00:11 UTC（05:00:11 BST）run `6d91710a99c8` 在模板修改前开始并最终成功；08:00 UTC 的 09:00 run 是修改后首个自动定时运行。
- `GenericRunManager._execute_loop()` 在 `_begin_retry()` 创建 profile buffer 时首次抛错。except 分支调用 `append_event()`，而没有 current retry 时它再次调用同一个 `plan.log_profile.new_buffer()`，第二次抛错逃出 worker，导致 `_finish_run()` 未执行。
- 当前 API 与 recent state 因此仍把 `12d74b2400e4` 报为 `running`、retry_count=0、updated_at 保持 08:00:02；实际 worker 已退出，服务进程仍 active，系统中无 maa-cli 进程。
- framework log 确认随后 12:30 BST 的 `t0800` 在 11:30:05/20/35/50 UTC 四次被拒绝，原因均为 `Run already active: 12d74b2400e4`；该分钟过后没有补跑，triggered state 也没有 `t0800`。因此僵尸状态已实际导致下一档定时运行错过。

## 只读检查

- 读取 schedule/settings、triggered state、recent run state、run event、framework log 和 systemd journal。
- 检查 systemd/process/API 当前状态。
- 审计 scheduler trigger path、template loader boundary contract、run manager begin/error/finalize path。
- 运行项目解释器直接加载模板，稳定复现上述 validation error。
- `git diff --check` 未通过，唯一报告是用户现有模板改动 `indent = 1  ` 的尾随空格；本轮未修改。

## 实施结果

- 修正 `log_template.toml`：删除 `blocks.fetch.start[0].tone`，保留 block 自身 `tone = "info"`；清理 `InfrastDormDoubleConfirmed` task rule 的尾随空格，保留用户将其从 global exact translation 移到 task rule 并缩进的意图。
- strict loader 仍用于 CLI/开发校验；新增 tolerant loader。TOML 已解码后按 field/lookup/translation/rule/boundary/block 隔离错误，未知 key 记录后忽略，其他有效片段继续编译。语法/I/O/encoding/version 错误仍作为整份不可解码。
- MAA 每次创建新 `RunLogBuffer` 都从磁盘重读 TOML，不再使用 `lru_cache`。有效模板保存为进程内 last-known-good；整份不可解码时复用，否则退到 plain/raw。
- `RunLogProfile.new_buffer()` 将可见日志配置器视为非关键展示扩展：异常时回滚其 block/context 改动、记录 framework exception、插入固定 fallback event 并继续创建 buffer，因此通用 run 不再因展示配置失败而拒绝执行。
- MAA partial/last-good/plain 三种错误分别只插入一条固定 framework event，带稳定 event key，经原有 retry/SSE 下发；详细诊断写 `data/debug/framework/framework.log`。
- 更新 `docs/log-templates.md`，明确 boundary 字段、每 retry 热读取、局部容错、last-known-good/plain fallback 和 SSE 行为。

## 验证与环境效果

- 相关模板/MAA 日志测试：38 passed。
- 完整 `.venv/bin/python -m pytest -q`：140 passed。
- `.venv/bin/python -m compileall -q src/maa_auto_panel tests` 与 `git diff --check` 通过。
- 回归覆盖：错误 boundary `tone` 被忽略但 boundary/其他翻译保留；单条坏 rule 不影响后一规则；新 buffer 读取保存后的新模板；语法损坏复用 last-known-good；首次损坏显示 raw；通用配置器抛错后真实 GenericRunManager command 仍 succeeded；固定错误 event 与后续日志同 buffer 可见。
- 重启前再次确认 `12d74b2400e4` 无 maa-cli/MaaCore/adb 进程。`maa-auto-panel-webui.service` 于 2026-07-14 13:22 UTC 重启，MainPID `26741 -> 9945`，当前 active/running，schedule API idle。
- 启动恢复已将僵尸 run `12d74b2400e4` 封口为 stopped，summary 为 `recovered_reason=backend restarted before run finalized`；没有补跑已错过的 12:30 档，也没有启动游戏任务。

## 后续 fetch tone 修正

- 用户指出“资源拉取诊断”内 Git stderr 两行显示为 warning，并说明此前误加 boundary `tone` 是为修复该展示。
- 复现确认 block 容器使用成功/信息语义色，但 message 因 `maa-cli:stderr` source 默认 tone 被渲染为 warning；历史 maintenance 数据表明旧展示曾为 info。
- 按用户要求不修改通用 tone 优先级，只在 `blocks.fetch.rules` 为 `From https://github.com/{repository}` 和 ` * branch ... -> FETCH_HEAD` 增加两条精确规则并声明 `tone = "info"`。未增加 catch-all，未知 fetch stderr 仍保留默认 warning/raw 证据。
- 截图等价输入回放确认两条 message 均为 info；完整测试更新为 141 passed，compileall 与 `git diff --check` 通过。模板按每个新 retry 热读取，无需重启服务。

## 后续基建伪产物清理

- 用户在 product lookup 中标记 `SkillLevel`、`MoodAddition`、`Drone`、`General`、`HR`，指出这些不是有实际含义的生产产物且原始日志顺序错误。
- raw stderr 审计确认这些值分别在训练室、控制中枢/宿舍、发电站、会客室、办公室的 `EnterFacility` 之前出现；是 MaaCore 复用 `ProductOfFacility` 携带房间占位类型，不应展示成按时间顺序的“设施产物”。stdout summary 未发现对应伪产物。
- 删除五项注释 lookup，并在通用 `ProductOfFacility: {product}` 规则之前加入五条精确 `action = "drop"`；保留 PureGold、SyntheticJade、Money、OriginStone 等真实产物翻译。未使用宽泛 catch-all。
- 严格模板校验为 4 blocks / 42 rules；回放确认伪产物无 message、真实赤金/龙门币保留。完整测试 142 passed，compileall 与 `git diff --check` 通过；热读取无需重启。
