# Session: 2026-07-14_0051-audit-maa-log-templates

- 目标：审计当前 MAA 日志模板及其调用边界，判断模板能否进一步简化，以及哪些通用逻辑适合内化到日志管线。
- 当前阶段：只读审计；未授权也未进行业务代码修改。
- 会话失误：误用 `rg -h` 试图隐藏文件名，实际触发帮助输出；已将通用安全默认值 `--no-filename` 记录到全局 lessons。
- 环境变化：更新了 `~/.codex/lessons.md`，新增上述 ripgrep CLI 陷阱。

## 审计结论

- 当前 `maa/log_templates.py` 804 行、通用 `logs/pipeline.py` 673 行。MAA 文件同时包含 source/block 注册、maa-cli timestamp/level/body 解析、任务生命周期、摘要与 git output 分块、中文文案、富文本/缩进以及 entry 列表装配。
- 四类 block：stderr task lifecycle、stdout run summary、stdout resource update、stderr fetch diagnostics；此外 stdout/stderr fallback 行走 MAA 单行翻译。
- 生产 `LiveRetry.to_dict()` 只暴露 `log_entries`；源码搜索未发现 `RunLogBuffer.output`/`RunLogBuffer.to_dict()` 的生产消费者。callback 返回字符串与 `format_time_prefix()` 属于可删除的旧投影。
- pipeline 的 `_trim()` 只由 `append_block()` 调用；task/summary/resource translators 直接 append active entry 后不会裁剪。复现：把 messages/lines 上限均设为 3，输入 5 条 Fight detail 并 Completed，最终 closed entry 仍为 5 messages/5 lines。
- 推荐边界：pipeline 负责原始行捕获、message 追加、time/tone/raw 默认、touch/generation、即时裁剪；MAA callback 返回 `LogMessage | None`/结构化 decision，不直接突变列表。MAA 特有 parser/matcher、expected task sequence、翻译、summary 聚合、报告折叠与 indent 继续留在 `maa/`。
- 次要清理：删除 no-op `_on_inert_close`；删除模板内与 pipeline 重复的 metadata helpers；让 summary/resource 的 definition defaults 真正生效，去掉重复 on_start 字段赋值；可由 source adapter 解析一次 MAA envelope，避免同一行在 matcher/translator 重复 regex。

## 验证

- 只读源码与引用搜索；未修改业务代码，未运行全套测试。
- 使用项目解释器执行最小复现，输出 `{'messages': 5, 'lines': 5, 'closed': True}`，确认 record limit 缺口。

## 用户质疑后的调用链复核

- 用户追问 MaaRunManager 是否消费该 API 判断任务成功。此前“没有消费者”的措辞指向不够醒目；精确结论仅限 `RunLogBuffer.output`/pipeline callback 返回的 rendered string。
- `process._emit_record()` 同时分发：`on_stream_output(stream, record)` 进入 visible-log 管线，`on_raw_line(stream, text)` 进入 MAA callback。
- manual runner 和 schedule runner 的 `on_raw_line` 都将原始 `maa-cli:stderr` 行送入独立 `MaaTaskResultCollector`；collector 解析 Start/Completed/Error/Stopped，`evaluate_attempt()` 使用 `return_code == 0 and all(task status == succeeded)` 判定 attempt。
- 因此成功判断确实消费日志原始行，但不读取 `RunLogBuffer.output`，也不以翻译后的 `log_entries` 为权威。后续重构必须保留 raw-result 分支；更合理的去重是在 MAA 领域共享 typed parser/event，而不是让成功判断依赖展示模板。
