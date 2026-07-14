# 日志翻译模板

MAA 可见日志的文字翻译集中在 `src/maa_auto_panel/maa/log_template.toml`。修改普通翻译时不需要改 Python。

## 最简单的翻译

模板根层除 `version` 外只有 `global` 和 `blocks`。确认一条原文在所有 block 中含义都相同时，写进全局表：

```toml
[global.translations]
Connected = "已连接"
ProductUnknown = "产物识别失败"
```

它是完整行匹配，不会替换长句中的一部分，也不需要填写 `id`。

只有某类 block 才适用的固定翻译放进对应组：

```toml
[blocks.task.translations]
SomeTaskMessage = "任务消息"
```

当前 blocks 按用途分为 `task`（任务块）、`summary`（运行摘要）、`resource`（资源更新）和 `fetch`（拉取诊断）。普通固定翻译和普通动态规则直接放在 `global`，不伪装成一个 `line` block。

## 带变量的规则

只有原文包含变化部分，或需要颜色、缩进、丢弃时，才写规则：

```toml
[[blocks.task.rules]]
match = "Use {count:int} medicine"
text = "使用 {count} 个理智药"
tone = "warning"
styles = { count = { tone = "warning", strong = true } }
```

占位符支持三种形式：

- `{value:text}`：任意文本；
- `{value:word}`：不含空白的一段文本；
- `{value:int}`：整数，并以整数值传给引擎。

`match` 必须匹配整行。规则按书写顺序尝试，因此更具体的规则应写在更宽泛的规则前面。

常用可选字段：

- `tone`：`default`、`success`、`warning`、`danger`、`info` 或 `theme`；
- `indent`：非负缩进级别；
- `action = "drop"`：识别该行但不显示；
- `lookups`：把占位符值交给 `[lookups.<name>]` 查表；
- `replacements`：对某个占位符做固定词语替换；
- `styles` 或 `segments`：设置局部颜色和粗体；
- `values`：提供输出中使用的固定字段。

## Block 展示、开始与结束

Block 名本身就是模板内的稳定名称，不需要额外填写人工 id 或事件名。展示属性和生命周期策略也直接写在 block 表中：

```toml
[blocks.task]
kind = "task"
title = "任务 {task.name}"
status = "running"
tone = "info"
panel_kind = "task"
entry = { name = "{task.name}", task_id = "{task.id}", source_name = "{task.source_name}" }
track_elapsed = true

[[blocks.task.start]]
source = "maa-cli:stderr"
match = "{source_name:word} Start"
values = { status = "running" }

[[blocks.task.end]]
source = "maa-cli:stderr"
match = "{source_name:word} Completed"
values = { status = "succeeded" }
```

常用 block 属性包括 `kind`、`title`、`status`、`tone`、`message_tone`、`panel_kind`、`entry`、`capture_start`、`emit_start`、`fallback_indent`、`track_elapsed`、`status_from_message_tone` 和 `close_on_metadata`。这些属性由通用模板 runtime 消费，MAA Python 层不再手工创建对应的 block matcher/translator。

`end` 条件默认消费结束行；当结束行同时是另一个 block 的开始时，可设置 `reprocess = true`，先关闭当前 block，再让同一行重新参加匹配。

## 原始行预处理

每个 source 可注册一个有状态的原始行预处理器。预处理器保留真正的 raw line，同时返回供模板匹配的正文和 `time`、`tone` 等元数据。MAA source 用它移除 `[时间 LEVEL]` envelope，因此模板只匹配正文。

OperBox/Depot 的 pretty JSON callback 也在这一层处理：检测到 JSON 开始后，同一 source 会持续静默，直到完整对象闭合。静默只影响结构化可见日志；diagnostics 和任务结果收集器仍接收原始输出。预处理状态属于单个 log buffer，不会跨 retry 或 run 泄漏。

## MAA 字段补全

任务配置里的显示名和 task id 不属于通用日志语义，因此由 MAA 自己的轻量字段监视器在 `task.start` / `task.end` 缺字段时补全；没有任务绑定时直接退回 maa-cli 的 source name。模板作者不需要编写这段逻辑。

结果判定仍由独立的 `MaaTaskResultCollector` 消费原始 stderr；修改可见日志模板不会改变任务成功或失败的判定。

## 修改后的检查

```bash
.venv/bin/maa-auto-panel validate-log-template
```

也可以在命令后传入其他 TOML 路径。校验失败会指出类似 `blocks.task.rules[3].text` 的位置；模板不使用人工 `id`。

## 实现模块边界

模板实现位于 `src/maa_auto_panel/logs/templates/`：

- `model.py`：纯模板数据结构、字段监视协议和校验异常；
- `engine.py`：字段补全、文本渲染、lookup/style/fold 与消息生成；
- `loader.py`：TOML 读取、严格 schema 校验和 pattern 编译；
- `runtime.py`：把已编译模板接入流式日志 pipeline。

调用方应直接导入定义所在模块；不要把 `__init__.py` 扩展成重新聚合全部类型的门面。
