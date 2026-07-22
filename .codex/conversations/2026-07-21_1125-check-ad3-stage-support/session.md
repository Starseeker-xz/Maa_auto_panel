# Session 2026-07-21_1125-check-ad3-stage-support

## Task

- 核实 MaaCore 是否能执行不在 `StageActivityV2` 远端列表中的关卡，具体为活动关卡 `AD-3`。

## Progress

- 已完成会话启动状态读取。
- Confirmed：本机 `maa-cli v0.7.5 / MaaCore v6.14.2` 的 `runtime/maa/data/maa/resource/tasks/Stages/AD.json` 明确定义了 `AD-3` 的活动入口、关卡 OCR 与滑动导航，因此 Core 资源支持 `Fight.stage = "AD-3"`。
- Confirmed：当前缓存 `StageActivityV2.json` 只列出 `SSReopen-AD`、`AD-8`、`AD-7`、`AD-6`；它是 GUI/面板候选列表，不是 Core 全部可导航关卡的清单。
- Confirmed：当前面板 UI 的活动关卡候选完全来自 `/api/maa/stages`，不提供自定义输入；后端 `_stage_info()` 还把未出现在远端列表、且符合两字母活动关格式的值视为已关闭。因此不能通过当前面板直接配置 `AD-3`。
- 可用绕过：游戏内手动停在 `AD-3` 关卡详情页，面板选择“当前/上次”；面板会向 Core 传空 `stage`，Core 从当前详情页开始并重复代理。
- 调查阶段未执行设备操作；后续按用户确认方案实施产品代码，整个会话始终未连接或操作设备。

## Implementation

- 新增随包发布的 `src/maa_auto_panel/maa/stage_aliases.json`，维护 MAA GUI 风格的常驻关卡中文显示名；别名只用于展示，不参与自定义输入归一。
- `MaaStageService` 对未知自定义关卡按“可尝试”处理，去除首尾空白后原样下发；已知活动/资源关仍按活动窗口和星期判断。
- Fight 编辑器通过 `x-allowCustom` 使用通用 `CreatableStringPicker`：同一 Popover 内搜索推荐项或显式创建自定义值；API 失败时仍可输入。
- 编辑器请求 `include_unavailable=true` 并滤除已过期活动，使跨星期资源关仍可预先加入候选计划。
- 更新 `docs/maa-runtime.md` 和 `docs/FRONTEND_AUDIT.md`，删除动态 option 无 fallback 的已解决问题。

## Verification

- `uvx ruff check src tests`：通过。
- `.venv/bin/python -m compileall -q src tests`：通过。
- `.venv/bin/python -m pytest -q`：159 passed（新增 7 个 stage/alias cases）。
- `npm --prefix frontend run build`：通过，无 500 kB warning。
- `git diff --check`：通过。
- wheel 构筑成功，`stage_aliases.json` 与 `log_template.toml` 均包含在包内。
- 无设备配置生成 smoke：自定义 `"  AD-4  "` 生成 `Fight.stage = "AD-4"`。
- Playwright（`domcontentloaded`）验证：GUI 别名可见；`AD-3` 可选；缺失推荐项 `AD-4` 可创建；拦截 stages API 后仍可将 `红票-5` 作为不转换的原始自定义值加入。没有保存浏览器草稿。
- 所有 manager 均非 active 后重启 `maa-auto-panel-webui.service`；服务当前 active。API 实测返回 GUI 中文别名且 `errors=[]`。

## Session observations and mistakes

- 本机没有 `sudo`，首次服务重启命令未执行；随后直接使用 `systemctl` 成功。已提升到全局 lessons。
- 本机没有 `unzip`，首次 wheel 内容检查在构筑完成后提前停止；改用 Python `zipfile` 验证。已提升到全局 lessons。
- 初次浏览器验收发现编辑器只请求今日开放关卡，无法显示截图中的跨星期候选；改为请求 unavailable 并保留运行时开放判断。
- 验收期间上游缓存热更新已将 `AD-3` 加入 `StageActivityV2.json`；因此最终同时用 `AD-4` 验证真正缺失推荐项的自定义路径。
- 一次新增测试的错误消息空格期望写错，修正测试后全量通过；实现行为未改。

## Follow-up: row action style and AD-3 provenance

- 用户报告可创建关卡行的编辑按钮在非 focus 状态仍有边框/底色，且激活样式与删除按钮不一致。
- Confirmed：`PopoverTrigger asChild` 覆盖了 Button 的 `data-slot="button"`，使其命中 `.jsonforms-surface button:not([data-slot="button"])` 裸按钮 fallback，强制出现 1px border/background。修复为 Popover Trigger 不覆盖子组件 slot，并抽出 `rowActionButtonClassName` 供编辑/删除/普通重命名操作共用；删除只叠加 destructive 颜色。
- Pointer 打开的 Popover 关闭时阻止 Radix 将焦点强制还给触发器，避免关闭后残留激活态；键盘打开仍保留默认焦点恢复。
- Playwright computed-style 验证：静止/关闭后的编辑与删除均 opacity 0.7、透明背景、0 border、无 shadow；编辑打开及删除 hover 均使用 accent 背景、0 border、无 shadow，删除保留红色图标语义。视觉截图：`scratch/row-actions-fixed.png`。
- Confirmed：`AD-3` 来自远端推荐值。2026-07-21 11:59 UTC 直读 API 的 `Last-Modified` 为 `2026-07-21 08:46:28 UTC`，其中明确包含 `AD-3` / `搓玉效率0.98`；下载内容与本机缓存 SHA-256 完全一致。没有任务配置含 `AD-3`，Core `Stages/AD.json` 只证明导航能力，不参与推荐列表构建。
- 一次视觉回归命令在 `frontend/` cwd 下又传 `npm --prefix frontend`，仅报不存在的 `frontend/frontend/package.json`，未产生文件或状态变化；随后使用正确 cwd 完成验证。

## Follow-up: framework-owned recommendation refresh

- Confirmed：编辑器请求只会让后端读取本地文件；原推荐缓存由 maa-cli 在 run 启动时更新，因 `XDG_CACHE_HOME=runtime/maa/cache` 而落在 `runtime/maa/cache/maa/StageActivityV2.json`。2026-07-21 远端 08:46 更新后，11:01/11:22/11:23 的编辑器请求仍命中旧文件，直到 11:30 run 启动才更新。
- 用户明确要求框架推荐数据与 runtime 功能提供方缓存分离。后端现以 `cache/maa/StageActivityV2.json` 和相邻 `.etag` 为自有缓存；maa-cli 的 runtime cache/data 只作为首次下载失败等场景的只读 fallback。
- API 读取推荐列表时至多每 10 分钟做一次 ETag 条件请求；进程内锁避免同一服务并发重复刷新，失败节流且继续使用旧缓存，写入使用原子替换。
- 验证：相关测试 15 passed；全量后端 162 passed；目标文件 Ruff 通过；`compileall -q src` 通过。真实无设备 smoke 成功写入 `cache/maa`，返回源为该文件、包含 `AD-3` 且 `errors=[]`。
- 部署状态：检查服务时发现 manual run `f2aa03f4f842`（General）仍在真实作战，未重启或干预服务；当前 systemd 进程仍是旧后端代码，待任务自然结束后需重启才加载本次实现。
- 环境陷阱：`.venv/bin/pytest` shebang 仍指向仓库旧路径，直接执行失败；按既有 project lesson 改用 `.venv/bin/python -m pytest`。
