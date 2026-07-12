# Session 2026-07-11_2105-audit-stream-no-newline

## Scope

- 只读复核 `docs/BACKEND_AUDIT.md` 的 P0“流读取可能被无换行输出阻塞”；未修改产品代码。

## Current implementation

- `src/maa_auto_panel/process.py::run_streaming_process` 仍把二进制 stdout/stderr 包装成 `TextIOWrapper`，用 `select.select(..., 0.2)` 等待可读后调用 `pipe.readline()`。
- pipe 可读只保证当前至少有字节或 EOF，不保证已有换行；子进程 flush partial text 后保持 pipe 打开时，`readline()` 会停在该调用内，主循环无法执行 timeout、stop escalation、force callback 或 `on_tick`。
- `GenericRunManager.stop()` / `force_stop()` 自身会直接向 process group 发 SIGTERM/SIGKILL，所以正常 API 显式停止通常不依赖被卡住的 reader callback；但 SIGTERM 被忽略后的 `stop_kill_seconds` 升级逻辑仍会被延迟。

## Reproduction

- 使用 `.venv/bin/python` 直接调用 `run_streaming_process`。
- 完全静默 child，sleep 3s，`runtime_kill_seconds=1`：1.00s 返回，return code -15，`timed_out=True`。
- child 先 `sys.stdout.write('partial'); flush()` 再 sleep 3s，同一 runtime timeout：3.01s 自然退出，return code 0，`timed_out=False`，没有 timeout event。
- 同一 partial child，0.5s 后令 `should_stop=True`：3.01s 自然退出，`stopped=False`。

## Recommended repair boundary

- 在统一进程执行器内改为 non-blocking binary fd + readiness selector / `os.read`，每个 stream 使用独立 UTF-8 incremental decoder。
- decoded chunks 可立即进入 raw diagnostic/visible streaming sink并更新 `last_output`；逐行消费者必须使用每流独立 line buffer，只对完整行回调，EOF 时 flush decoder 和最后 partial line。
- 每次 read 必须有 chunk 上限并在循环中公平处理 stdout/stderr，避免持续高吞吐单流饿死 timeout/tick；partial line buffer 需设有界策略，避免超长无换行输出造成无界内存。
- 测试至少覆盖 stdout/stderr partial output、跨 chunk UTF-8、CR/LF 边界、超长无换行、runtime/no-output timeout、stop escalation、force-stop、EOF partial flush 与双流公平性。

## Implementation and verification

- `process.py` 已改为 non-blocking binary `os.read`、每流 incremental UTF-8 decoder 与 1 MiB bounded partial-line buffer。
- 参考既有 `data/debug/framework/external/maa-cli`：诊断文件为 stdout/stderr 原文本连续追加，抽样最长逻辑行约 15.9 KiB，未发现 CR progress。实现保持旧逻辑行 callback/chunk 边界及合并日志 stream header/CRLF/EOF partial 格式；bytes 到达会独立刷新 silence timer。
- 定向 process/run-manager/shutdown：13 passed；增加超长无换行有界切段后，完整后端最终为 98 passed；compileall 与 `git diff --check` 通过。
- P2 逻辑路径同步实施。停服前确认 current run 为 succeeded，无 active run；迁移前备份为 `scratch/pre-logical-path-migration.tar.gz`。
- 一次性迁移脚本首次运行因对 tuple 调用 `.glob()` 报错，未改任何数据；修正为逐 root 遍历后成功原子改写 68 files，旧引用扫描为 0。这是本轮 session-only 脚本错误。
- systemd 最终已重启为 PID 57764，active。`/api/history/runs/84887fbd6973` 回读 succeeded、1 retry、12 log entries、3 events；PackageManager 正确解析缓存中 160/170 两个 APK。
