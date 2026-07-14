# Project Lessons

只记录未来仍容易复发的项目级陷阱。每项带来源会话。

## Run lifecycle and persistence

- `2026-07-13_1541-review-incomplete-session`: durable run state 是恢复权威；终态必须先持久化再发布 live/SSE。持续写失败应 fail-closed，post-finish retention/notification 必须与核心提交隔离。
- `2026-07-13_1500-audit-run-architecture`: `GenericRunManager` 唯一拥有 live state、retry loop、锁和资源申请时序；领域 callback 只接收受限上下文。通用 manager 不得按 manual/schedule/tool/maintenance/MAA 分支。
- `2026-07-10_0416-full-project-audit`: pipe 可读不代表 `TextIOWrapper.readline()` 不阻塞。流式进程必须 non-blocking 读 bytes、增量解码、自行分行，并覆盖 partial output、timeout、stop 和 process-group descendant。
- `2026-07-10_2207-graceful-shutdown`: 应用关闭使用共享 absolute deadline；先广播停止语义并唤醒 SSE/资源等待，再 join，最后 force-stop。不要给每个 manager 顺序分配完整 timeout。
- `2026-07-12_0055-fix-retention-frontend-split`: retention 以 run 为 ownership 单元；先原子移除索引，再删除明确 owned artifact。unknown/shared/external path 不得仅因“看起来是本地路径”而删除。
- `2026-07-14_2057-full-code-audit`: scheduler 触发不能只比较轮询瞬间的当前分钟。高可用调度必须持久化 scan cursor、扫描 due window，并以 schedule/entry/game-day/scheduled-at 幂等去重。

## Logs, state and configuration

- `2026-07-14_1304-investigate-9am-schedule`: 可插拔展示配置永远不能阻止 run 执行、错误报告或终态收尾。模板保持 strict 离线校验，同时在 runtime 使用片段容错与 last-known-good/plain fallback。
- `2026-07-14_0244-optimize-log-template-migration`: 可见日志与结果判定必须分支：模板/pipeline 可翻译、折叠或静默展示，但 diagnostics 和 raw result collector 保留原始证据。未知行走 raw fallback，不用 catch-all 伪装覆盖。
- `2026-07-14_0051-audit-maa-log-templates`: 结构化日志只能通过 pipeline 的统一 append API 更新，以保证 generation/touch/有界裁剪一致；不要由模板 runtime 直接突变 entry 列表。
- `2026-07-13_1500-audit-run-architecture`: HTTP 状态由语义异常决定，不能全局把 builtin `ValueError/KeyError/FileNotFoundError/RuntimeError` 映射成 4xx。
- `2026-07-10_0416-full-project-audit`: durable JSON/TOML parse failure 不能静默当空状态后覆盖。隔离 corrupt 文件、记录诊断并阻止破坏性写入；APK manifest 同样适用。
- `2026-07-10_1752-audit-data-paths`: 项目未发布时不为旧布局/API/数据添加 migration 或兼容读取；对本机数据做一次性调整，并直接收敛到最终结构。

## Frontend

- `2026-07-14_2057-full-code-audit`: 同一 manager 的 run 可按实体过滤“显示内容”，但 start/stop availability 必须依据未过滤的 global manager state，不能把其他实体的 active run 投影成 idle。
- `2026-07-14_2057-full-code-audit`: 通用 `LogPane` 不得从翻译后的人类日志反解析领域状态；运行详情来自结构化 metadata/artifact/detail descriptor。
- `2026-07-14_2057-full-code-audit`: 动态 option descriptor 必须有真实的 API 失败/空结果 fallback；无选项 Select 不等于 free-text。需要可输入选择时复用成熟 combobox primitive。
- `2026-07-14_2057-full-code-audit`: descriptor 字段必须有实际 renderer/行为消费者。未实现的 `kind` 应删除，不保留“看似通用”的半成品契约。
- `2026-07-11_1805-consolidate-audits`: 实现基础交互前先检查现有 shadcn/Radix/Sonner；Dialog/Popover/Tabs/Sheet/Toast/Tooltip 等基础设施优先复用组件库，业务组件只保留领域状态和薄样式。
- `2026-07-01_1506-sse-log-delta`: Playwright 不要等待含 EventSource 页面的 `networkidle`；使用 `domcontentloaded` 与目标状态断言。

## Environment

- `2026-07-13_2243-frontend-retry-block`: 后端代码变化后，只有在确认无 active run 时才重启 `maa-auto-panel-webui.service`；仅构筑前端会造成新 UI 连接旧 Python 进程。
- `2026-07-11_1805-consolidate-audits`: 判断 MAA runtime 使用 `scripts/maa-env maa version` 或 `MaaRuntime.env()` 等价环境；直接运行 binary 会因缺少 MAA/XDG 环境误报损坏。
- `2026-07-10_0416-full-project-audit`: 仓库移动后 venv console-script shebang/editable metadata 可能仍指向旧路径；验证优先用 `.venv/bin/python -m ...`，必要时重建 venv。
- `2026-07-10_0416-full-project-audit`: systemd/dev 与 Compose 不得并行连接同一设备或共享持久根；scheduler/coordinator/store 当前不支持多进程副本。
