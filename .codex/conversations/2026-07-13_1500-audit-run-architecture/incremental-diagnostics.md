# Subagent: incremental-diagnostics

父会话：`2026-07-13_1500-audit-run-architecture`

## 审计结论

- Confirmed：旧 `Diagnostics.maacore_log_offset()` / `capture_maacore_log()` 固定读取 `state_home/maa/debug/asst.log`，固定写入 `maacore` 目录，使 framework diagnostics 知道 MaaCore 安装布局。
- Confirmed：旧捕捉逻辑把新增 bytes 以 UTF-8 replacement decode 后重新编码，会改变非 UTF-8 原始诊断内容。
- Confirmed：manual 与 schedule callback 已经分别按 retry 保存 offset，适合由 MAA 领域边界提供源路径并调用通用 diagnostics 操作；`GenericRunManager` 无需参与。

## 实现

- `Diagnostics.capture_file_increment(source, start_offset, capture_id=...)`：
  - 从调用方给出的任意文件读取 offset 后的 bytes；
  - 源不存在返回空结果与 offset 0；
  - offset 为负数或超过当前大小时按文件被截断处理，从 0 捕捉；
  - 原子保存原始 bytes 到 framework `external/incremental`；
  - 返回 `IncrementalLogCapture(log_file, next_offset, captured_bytes)`。
- 删除旧 MaaCore 专项 API、固定源路径、专项 capture retention 命名及 Diagnostics 内 MaaCore debug rotation/prune。
- manual/scheduler callbacks 在 MAA 领域解析 `asst.log`，于 command 构建时记录 offset，attempt 结束时调用通用捕捉 API；artifact key 暂保持领域已有的 `maacore_log_file`。

## 验证

- `.venv/bin/python -m pytest -q tests/test_run_state_and_diagnostics.py -k 'diagnostics_captures or diagnostics_increment or diagnostics_retention'`：3 passed。
- `.venv/bin/python -m compileall -q src/maa_auto_panel/diagnostics.py src/maa_auto_panel/maa/runner.py src/maa_auto_panel/scheduler/service.py`：passed。
- `git diff --check`（本子任务文件）：passed。
- 同一测试文件全跑时，5 个既有测试因并行改动将 `RunStateStore` 构造器收窄为显式 paths/references 而失败；与增量捕捉无关，需父代理集成后按新构造签名重跑。

## 值得保留的项目陷阱

- 增量外部日志捕捉应复制原始 bytes，不能先用 replacement decoding 转换，否则诊断证据会被不可逆修改。
- `next_offset` 应以已打开文件完成读取后的 `tell()` 为准；只返回读取前的 `stat().st_size` 会在并发追加时造成 offset/内容边界含糊。
- 仅有数值 offset 无法识别“源文件被替换且新文件大小仍大于旧 offset”的 rotation。若未来需要严格无遗漏轮转，应让领域层同时保存 inode/file identity，而不是把特定轮转语义塞回 Diagnostics。
