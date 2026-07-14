# Session 2026-07-14_0244-optimize-log-template-migration

## Scope

- 完成 MAA 日志 block runtime 迁移，并将 source 注册上浮到通用运行日志 profile。
- 增加有状态 raw-line 预处理，静默 OperBox/Depot pretty JSON。

## Environment effects

- 修改日志模板/runtime/profile 相关源码、模板、测试和文档；未修改依赖，未启动或重启服务。

## Work log

- 已按项目约定读取全局 lessons/memory index，以及项目 history、lessons、conversation index。
- 当前工作树中的 MAA 模板迁移尚未提交；`maa/log_templates.py` 已由旧版约 804 行降至 510 行，TOML 为 363 行，通用模板编译器为 769 行。
- 定向验证：`tests/test_log_templates.py tests/test_maa_logs.py` 共 30 passed；模板 CLI 报告 4 blocks / 37 rules；`git diff --check` 通过。
- 子代理 `raw_template_audit` 审计 174 个 raw 文件、7,866 行，报告见 `raw_template_audit.md`；据此删除 6 条冗余规则，模板现为 31 条动态规则。
- 新增通用 `TemplateBlockRuntime`、block 展示/生命周期 schema、有状态 source preprocessor、boundary reprocess；`RunLogProfile` 以 `source_specs` 声明 source。
- MAA 文件最终 148 行，只保留字段监视、source specs、runtime 初始化、envelope/OperBox/Depot JSON 预处理。
- 完整验证 133 passed；compileall、模板 CLI、diff check 通过；174 个 raw stdout/stderr 文件逐个 replay，共生成 1,910 entries，无异常。
- 后续精简删除纯文本 output 投影及其 max/chunk/terminal emit 状态；pipeline append/flush 改为结构化 generation 变化布尔值。
- 将 1,195 行 `logs/templates.py` 删除并拆成 `logs/templates/{model,engine,loader,runtime}.py`；最大文件为 429 行，无聚合 re-export。

## Current conclusions

- block runtime 迁移已完成；task/summary/resource/fetch 的匹配、翻译、状态和关闭策略均由模板及通用 runtime 驱动。
- Stateful preprocessor 状态必须留在 pipeline 的 per-source state；共享 profile/spec 只保存无状态函数引用。
- JSON 静默仅影响结构化可见日志，diagnostics 和 raw result collector 继续收到原文。
- 纯文本 `output` 投影已删除；live/history/API 继续只消费 `log_entries`。
