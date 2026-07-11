# Project History

面向无上下文后续会话的当前项目交接。仅记录仍有效的事实、风险和方向。
置信度：Confirmed / Likely / Hypothesis / Unknown。

## Current repository

- Confirmed (`2026-07-10_0004-complete-rename-maa-auto-panel`): 项目名 `Maa Auto Panel`；Python 包 `maa_auto_panel`；distribution/CLI slug `maa-auto-panel`；入口 `maa-auto-panel = maa_auto_panel.cli:main`。仓库 `/root/Maa_auto_panel`，远端 `Starseeker-xz/Maa_auto_panel`。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): 当前通用框架目录为 `data/config/framework`、`data/state/framework`、`data/debug/framework`、`data/history/framework`；MAA 安装已从 data 拆为独立 `runtime/maa`；download cache 为 `cache/downloads`。任务 metadata namespace 为 `framework`；runtime placeholder 为 `__framework_runtime__:*`；schema 扩展键为 `x-frameworkManaged`。
- Confirmed (`2026-07-10_0416-full-project-audit`): 2026-07-10 工作区含尚未提交的大规模重命名/通用化改动。后续操作必须保留这些用户改动，不得按 HEAD 旧路径判断当前架构。
- Confirmed (`2026-07-10_0416-full-project-audit`): 最新完整审计是根目录 `PROJECT_AUDIT.md`。旧 `BACKEND_AUDIT.md`、`FRONTEND_AUDIT.md` 和此前审计结论不再是当前依据。

## Product direction

- Confirmed (`2026-07-11_0111-audit-container-plan`): 容器文件当前用于固化未来部署边界，不代表立即生产切换。未经用户明确要求不得 build/up Docker；日常开发继续使用现有 systemd 服务重启。当前 dev/systemd 与 Docker 实例绝不并行连接同一 redroid 或共享 data；若未来需要并行开发，必须隔离设备、data/cache/ADB state 并禁用开发 scheduler。
- Confirmed (`2026-07-10_0416-full-project-audit`): 当前功能闭环已基本完成，主要工作转为架构重整、长期运行可靠性与通用扩展。
- Confirmed (`2026-07-10_0416-full-project-audit`): 目标是让 MAA/maa-cli 成为自动化框架的一个 integration，并支持未来其他 maa-cli 类工具及正式自定义脚本接口。
- Confirmed (`2026-07-10_0416-full-project-audit`): 当前不需要数据库、微服务或动态第三方插件加载器。优先顺序是运行/安全基线 → 框架上下文解耦 → 内部 Action/Integration registry → 第二 integration 验证。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): 容器化目标为单 panel 容器、外部 TCP redroid、普通 bridge 网络、非 privileged、单实例；框架 `data`、integration `runtime`、download cache、ADB credential 使用四个独立持久化边界；`runtime/maa` 与框架 data 和应用镜像版本解耦。
- Confirmed (`2026-07-10_0416-full-project-audit`): 用户明确产品威胁模型为“可信内网、单用户”，不需要为公网/多租户假设引入登录、token、session、RBAC、用户数据库或认证反代。网络边界由 LAN/防火墙和 Compose publish 地址承担；若产品前提未来改变再单独评估认证。

## Current architecture

- Confirmed (`2026-07-09_1512-run-manager-generalize`): 手动、定时、工具、维护运行统一使用 `GenericRunManager` 与 `LiveRun`/`LiveRetry`；通用 payload 为基础字段 + `metadata` + `artifacts`，live/history 均为 `{run, retries}`。
- Confirmed (`2026-07-06_0037-callback-run-manager`): manager 拥有 command/retry/lifecycle；领域只通过 callbacks 决定动态命令、raw-line 消费、attempt 结果和是否继续。不要恢复 driver-owned retry loop。
- Confirmed (`2026-07-10_0416-full-project-audit`): `RunCoordinator` 跨四类 manager 共享，当前主要仲裁相同 ADB address；schedule auto > schedule manual > normal。
- Confirmed (`2026-07-10_0416-full-project-audit`): 状态、history、diagnostics、framework logging 分离。保持该分离；scheduler daily stats/trigger state 继续留在 scheduler domain。
- Confirmed (`2026-07-10_0416-full-project-audit`): 当前“通用层”仍接收 `MaaRuntime`。应拆成 `FrameworkPaths`、`ProcessContext`、`MaaInstallation`，使 process/run manager/store/diagnostics 不再依赖 `maa.*`。
- Confirmed (`2026-07-10_1752-audit-data-paths`): 已新增 `ApplicationPaths`、`FrameworkPaths`、`CachePaths`、`MaaInstallation`、`PathLayout`；`MaaRuntime` 是组合这些路径的 runtime aggregate。路径所有权已拆开，但 process/run manager/store/diagnostics 的类型依赖仍可在后续进一步收窄。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): `FrameworkPaths` 不再包含 runtime；新增 `MAA_AUTO_PANEL_RUNTIME_DIR`/`--runtime-dir`，`MaaInstallation` 从独立 runtime root 派生。容器对应 `/app/runtime` 和 `MAA_PANEL_RUNTIME_PATH` bind mount。本机已一次性迁移为 `runtime/maa`，systemd 恢复 active，API idle 与 `maa version` 验证通过。
- Confirmed (`2026-07-10_2207-graceful-shutdown`): FastAPI lifespan 现在拥有 scheduler/WebServices 生命周期。SIGTERM 先结束 SSE，再停止 scheduler、关闭 coordinator、并行通知四类 manager；正常/强停共享 60s/15s absolute deadline，最后 flush diagnostics 和 join 非 daemon 线程。
- Confirmed (`2026-07-10_2207-graceful-shutdown`): 所有外部 command 使用独立 POSIX session；stop/force-stop 分别向完整 process group 发送 SIGTERM/SIGKILL，测试确认 SIGTERM-ignoring descendant 会被清理。
- Confirmed (`2026-07-10_0416-full-project-audit`): 自定义脚本当前只有 schedule restart hook；工具 registry 仅在 `ToolRunManager` 中硬编码 `game-update`。未来以本地可信 manifest + ActionSpec 扩展，不应先开放 Web 任意脚本上传。

## Active high-priority findings

- Confirmed (`2026-07-11_0111-audit-container-plan`): WebUI 手动更新后宿主 `maa version` 可报告 maa-cli 0.7.5 / MaaCore 6.14.0，但官方 stable 安装脚本 + 全新容器卷 `maa install --batch stable` 仍产生混合 Linux runtime：core 依赖 OpenCV `.411`，ADB control plugin 依赖 `.412`，artifact 仅含 `.411`。`maa version` 未加载 ADB plugin，不能作为设备任务可用证明。基础应用镜像不受阻；真实设备 smoke 暂缓，禁止伪造 SONAME symlink。
- Confirmed (`2026-07-10_0416-full-project-audit`): 服务以 root 身份监听 `0.0.0.0:8000` 是裸机测试方式；在可信内网单用户前提下，无 authentication scheme 不视为缺陷。容器仍应避免 privileged/Docker socket/host network，并用低成本专用 UID/capability 收缩宿主影响面。
- Confirmed (`2026-07-10_0416-full-project-audit`): 上述 root/监听状态是裸机测试方式，不能原样判定为目标容器缺陷。容器实施时重新以 UID/capability/volume/published port 评估；TCP ADB 不需要 privileged、host network 或宿主 USB mount。
- Confirmed (`2026-07-10_0416-full-project-audit`): maintenance update 未声明 runtime resource，可与活跃 MAA run 并发修改 maa-cli/MaaCore/resource。资源模型应支持 shared/exclusive claim。
- Confirmed (`2026-07-10_0416-full-project-audit`): `select()` 后调用 `TextIOWrapper.readline()` 会被无换行输出阻塞。实测 runtime kill=1s 的 partial-line child 运行 3.01s 后正常退出且 `timed_out=False`。必须改为 non-blocking byte read + incremental decode。
- Confirmed (`2026-07-10_2207-graceful-shutdown`): lifespan/shutdown/process-group P1 已修复。真实 systemd + SSE 验收为 586ms、`inactive/success`、`ExecMainStatus=0`；live unit `TimeoutStopSec=120`，服务随后恢复 active/idle。
- Confirmed (`2026-07-10_0416-full-project-audit`): coordinator 同优先级冲突会无限等待；HTTP start 可能占住 worker。API 应 non-blocking 409，或建立显式 queued run。
- Confirmed (`2026-07-10_0416-full-project-audit`): `GenericRunManager._runs/_plans` 不清理；run history index 有上限但 history JSON 不删除；长期运行会增长内存和磁盘。
- Confirmed (`2026-07-10_0416-full-project-audit`): active retry 只在 seal 时持久化；崩溃恢复会丢失当前 retry 的结构化可见日志。建议节流 checkpoint。
- Confirmed (`2026-07-10_0416-full-project-audit`): game updater 只校验 HTTP/Content-Length/versionCode，没有 APK hash、package identity 或 signing certificate 验证。

## Other active issues

- Confirmed (`2026-07-02_2144-manual-stop-delay`): MaaCore 冷 ADB server 路径曾出现约 60 秒 `adb devices` 延迟。保持本地 adb server、`kill_adb_on_exit=false` 可规避；详细复现仍保留为活跃会话。
- Confirmed (`2026-06-30_2318-gpu-ocr-research`): 当时的 MaaCore build 只有 CPU ONNX Runtime provider。升级 MaaCore 后需重新验证 GPU OCR，旧会话已归档。
- Confirmed (`2026-07-10_1752-audit-data-paths`): `.venv/bin/maa-auto-panel` shebang 已指向当前 `/root/Maa_auto_panel/.venv/bin/python3`，systemd 的 `uv run maa-auto-panel` 可重启；当前环境没有 Ruff executable/module，pytest 使用 `.venv/bin/python -m pytest`。
- Confirmed (`2026-07-10_0416-full-project-audit`): 前端无自动测试；单 JS bundle 768.47 kB。应先补高风险 state/hook 测试，再做 route lazy loading。
- Confirmed (`2026-07-10_0416-full-project-audit`): 当前 lock 中 `idna`、`lxml`、`requests`、`soupsieve`、`urllib3` 有 pip-audit 公告；多项实际调用面较低，但 urllib streaming download 更相关。刷新 lock 后需跑 game update smoke test。

## Verification baseline

- Confirmed (`2026-07-11_0111-audit-container-plan`): 基础容器文件已实现并构建 `maa-auto-panel:local`（context 1.80 MB，image 325 MB，UID/GID 10001）。最终镜像 CLI/import/frontend/schema/adb/git/curl 通过；隔离临时卷 Web 首页与 SIGTERM exit 0 通过；测试后 systemd 恢复 active，未启动常驻 panel 容器。
- Confirmed (`2026-07-10_0416-full-project-audit`): Ruff passed；compileall passed；`.venv/bin/python -m pytest -q` 为 66 passed；Vulture 无发现；frontend build passed；`npm audit` 0 vulnerabilities；`git diff --check` passed。
- Confirmed (`2026-07-10_0416-full-project-audit`): 运行环境审计时 scheduled run 正在执行，未被审计操作中断；systemd unit 为 `maa-auto-panel-webui.service`，disabled 但 active。

## Documentation and state

- Confirmed (`2026-07-10_0416-full-project-audit`): `.codex/conversations/` 只保留当前审计、当前命名状态和仍未解决的 ADB 延迟会话。其余 39 个完成/被覆盖会话统一归档到 `~/.codex/archived_sessions/maa-auto-panel/`。
- Confirmed (`2026-07-10_0416-full-project-audit`): 架构/运行/路径/API 变化时检查 `README.md`、`docs/README.md`、`docs/maa-runtime.md`、`docs/architecture-direction.md` 和本文件。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): 路径布局区分四类所有权：`data_root` 只保存框架拥有的 config/state/history/debug；`runtime_root` 保存 integration 安装与自身 XDG 状态；downloads 是独立可重建 cache；ADB 客户端密钥使用独立 `adb-state` volume。
- Confirmed (`2026-07-11_0203-separate-runtime-and-agent-doc`): `docs/AGENT_PROJECT_GUIDE.md` 是面向无上下文 agent 的中文高层交接，覆盖产品边界、技术栈、模块地图、骨干运行链路、状态分层和当前风险；执行规则仍以根 `AGENTS.md` 与 `.codex` 状态为准。
- Confirmed (`2026-07-10_1752-audit-data-paths`): 本机目录已一次性调整到最终 `data/` 与 `cache/downloads/` 布局；服务已恢复 active。config API、历史详情、两个 APK cache path、maa-cli/MaaCore version 均验证通过。项目未发布，不保留迁移 CLI、layout version 或旧布局兼容逻辑。
- Confirmed (`2026-07-10_1752-audit-data-paths`): 即使 `/api/runs/current` 为 idle，systemd stop 仍在 20 秒后 SIGKILL。journal 直接停在 Uvicorn `Waiting for connections to close`，很可能有 WebUI SSE/EventSource 长连接未及时结束；idle 只表示没有 MAA run，不代表没有 HTTP 长连接或后台线程。迁移在 unit 完全停止后才开始。
