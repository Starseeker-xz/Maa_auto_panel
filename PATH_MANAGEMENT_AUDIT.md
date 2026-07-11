# Maa Auto Panel 路径管理审计

状态：第一版路径重构与本机数据迁移已完成  
来源会话：`2026-07-10_1752-audit-data-paths`  
审计日期：2026-07-10

## 1. 结论

框架拥有的持久数据收敛到可配置的 `data_root`；integration 的安装和自身状态使用独立 `runtime_root`。开发环境默认使用仓库内 `data/` 与 `runtime/`，容器环境分别挂载到 `/app/data` 和 `/app/runtime`。目录内部继续按职责和保留策略分区，不能把 config、state、history、debug 混放。

`data_root` 不是“所有需要持久化的文件”的总称。integration runtime、可重新下载的 APK/patch cache、ADB 客户端密钥都应与框架 data 分开。

推荐第一版布局：

```text
data/
  config/
    framework/
    maa/
  state/
    framework/
  history/
    framework/
  debug/
    framework/
runtime/
  maa/
    bin/
    data/
    cache/
    state/
    generated-configs/
    run-logs/
cache/
  downloads/

# 容器独立 named volume，不放进应用 data_root
/home/panel/.android/
```

顶层 `runtime/` 表示集成运行时根；`runtime/maa/data` 是 maa-cli 的 XDG data home。后一个 `data` 属于上游 XDG 布局，语义明确，不应为了外观改写。

本机已按该布局完成迁移。框架 data、integration runtime、大体积 download cache 和 ADB credential state 分别使用可选择不同保留策略的 volume。应用代码与静态资产可保持只读。

## 2. 当前路径全景

当前主要路径由 `MaaRuntime(repo_root)` 聚合，但 data/runtime/cache 均可独立覆盖：

| 当前路径 | 所有者/内容 | 生命周期 | 当前规模 | 建议位置 |
|---|---|---|---:|---|
| `config/maa` | maa-cli profiles/tasks/infrast/cli、回收站 | 用户配置，必须备份 | 约 124 KiB | `data/config/maa` |
| `config/framework` | settings/schedules/scripts、回收站 | 用户配置，必须备份 | 约 4 KiB | `data/config/framework` |
| `state/framework` | recent run index、retry index、scheduler 触发与日统计 | 可恢复运行状态，必须持久化 | 约 440 KiB | `data/state/framework` |
| `history/framework` | 完整结构化 run/retry history | 业务历史，建议备份 | 约 2.8 MiB | `data/history/framework` |
| `debug/framework` | framework/event/external process/MaaCore diagnostics | 可删诊断数据 | 约 106 MiB | `data/debug/framework` |
| `runtime/maa` | maa-cli、MaaCore、resource、XDG cache/state、生成配置 | 框架无关的集成安装与运行数据 | 约 1.3 GiB | `runtime/maa` |
| `downloads` | APK、patch、manifest | 可重建的大文件缓存，不是框架运行依赖 | 约 4.0 GiB | `cache/downloads`，独立 cache root/volume |
| `$HOME/.android` | 主要是 ADB 客户端 `adbkey`、`adbkey.pub` | 外部设备授权凭据；删除后通常需重新授权 | 仓库外 | 保持 `/home/panel/.android`，使用独立 `adb-state` volume |
| `TEMP` | 用户临时输入；当前业务代码未引用 | 非托管临时数据 | 约 4 KiB | 不自动迁移；以后产品化可用 `data/imports` |
| `frontend/dist` | Web 静态资产 | 构建产物，只读 | 不属于数据 | 应用资产目录 |
| `docs/maa-cli/schemas` | 运行时 schema | 随应用版本发布，只读 | 不属于数据 | 应用资产目录 |

规模来自本次只读 `du` 采样，运行中的服务可能继续增长。

## 3. 主要发现

### P1：应用根、数据根、MAA 安装被一个对象混为一体

[`MaaRuntime`](src/maa_auto_panel/maa/runtime.py) 只接收 `repo_root`，同时推导应用资产、框架 config/state/history/debug、MAA binary/XDG/generated config，以及子进程 cwd/env。

这导致路径不能独立覆盖，应用必须知道源码仓库形态。`find_repo_root()` 查找不到 `pyproject.toml + src/maa_auto_panel` 时还会静默返回当前工作目录；从 wheel、不同 cwd 或精简容器启动时，数据可能被写到意外位置。

路径所有权现已拆成四个不可变对象：

```text
ApplicationPaths
  app_root / frontend_dist / schema_dir

FrameworkPaths
  data_root / config_dir / state_dir / history_dir / debug_dir

CachePaths
  cache_root / downloads_dir

MaaInstallation
  root / binary / config_dir
  xdg_data_home / xdg_cache_home / xdg_state_home
  generated_config_dir
```

`MaaRuntime` 暂时保留为组合视图；后续继续把通用 process/store/diagnostics 的参数类型收窄到其真正需要的路径对象。

`process` 只接收 `cwd/env`，store/diagnostics 只接收 `FrameworkPaths`，MAA runner/maintenance 才接收 `MaaInstallation`。

### P1：可写目录分散，容器挂载与备份边界过多

当前至少有六个仓库内可写根，另有 `$HOME/.android`。应按所有权和可恢复性收敛成四类边界，而不是强塞进一个父目录：

1. `data_root`：框架拥有的数据，包括 config/state/history/debug。
2. `runtime_root`：集成工具的安装、resource 与自身 XDG 状态。
3. `cache_root`：删除后可重新生成或下载的数据；当前主要是 downloads。
4. `adb-state`：ADB 客户端授权密钥的独立容器 volume，不扩展成通用持久 HOME。

统一的是父边界，不是数据等级。备份仍应区分：

- 必须：`data/config`、`data/state`；
- 建议：`history`；runtime 依据可重装性单独决定；
- 可选：`debug`；
- 单独按凭据策略保存：`adb-state`；
- 通常不备份：`cache/downloads`、runtime cache/generated configs。

### P1：持久记录保存物理路径，移动目录会使旧数据失效

当前 diagnostics、config、trash、history artifact 广泛使用相对 `repo_root` 的字符串。`RunStateStore` 还会把 `log_entries_file` 重新用 `repo_root / stored_value` 解析。现场数据中发现约：

- 932 处 `debug/...` 引用；
- 215 处 `runtime/...` 引用；
- 110 处 `history/...` 引用。

更直接的已发生故障是 `downloads/manifest.json`：两个已验证 APK 仍记录重命名前的 `/root/Linux_maa/downloads/...` 绝对路径，当前 `get_verified_package_path()` 会把它们判断为不存在。

建议以后持久化逻辑引用，不持久化部署相关物理路径：

```json
{"root": "debug", "path": "framework/external/maa-cli/<run-id>.stdout.log"}
{"root": "runtime", "path": "maa/generated-configs/<run-id>"}
{"root": "download-cache", "path": "arknights_bilibili_v170_patched.apk"}
```

至少也应统一保存 `data_root` 相对路径，并由单一 `PathResolver` 校验、解析。API 若只为展示路径，应明确返回 `display_path`，不能让展示字符串兼任后续文件定位 key。

迁移时必须改写 state/history/trash/download manifest 中的旧引用；只移动目录不够。

### P1：只读资产也依赖仓库相对位置

schema validator 从 `repo_root/docs/maa-cli/schemas` 读取 schema，Web 从 `repo_root/frontend/dist` 提供页面。它们属于应用版本资产，不属于 `data/`，应通过安装包资源或显式 `app_root` 定位。

配置文件中的 `$schema` 又使用相对文件路径。将 config 下移一级后，现有 `../../docs/...`、`../../../docs/...` 将指向错误位置；当前仓库中还存在一份 `config/maa/tasks/full-current.toml` 使用另一套 `../../schemas/...`。迁移应统一重写 `$schema`，或改成稳定的应用内 schema URI，不能仅更新默认模板。

### P2：相同数据存在多套路径来源

- Web 工具显式使用 `repo_root/downloads`；独立 game CLI 默认使用相对 cwd 的 `downloads`。
- `scripts/maa-env` 重复硬编码 config 与三个 XDG home。
- tests 直接断言旧目录字符串。
- `create_services(repo_root)` 只有仓库根覆盖，没有 `data_root/app_root` 覆盖。

建议路径只在 composition root 构造一次。脚本、CLI、Web 和测试均消费同一套路径对象；CLI 分别提供 `--data-dir`、`--cache-dir`，环境变量提供 `MAA_AUTO_PANEL_DATA_DIR`、`MAA_AUTO_PANEL_CACHE_DIR`。

```text
显式函数/CLI 参数 > 对应环境变量 > 开发默认 <repo>/data 或 <repo>/cache
```

容器中显式设置为 `/app/data` 或 `/data`，不要依赖 cwd 猜测。

### P2：目录创建和可写性检查分散在各服务构造器

Diagnostics、RunStateStore、ConfigManager、ScheduleConfigManager、ScheduleScriptManager、PackageManager 等各自 `mkdir()`。启动到中途才可能发现某个目录不可写，且没有统一列出真实写路径。

后续可增加一次性 `FrameworkPaths.validate_writable()`：检查已注册目录的类型与可写性，并报告规范化后的 app/data/runtime root。启动检查不应触碰网络或自动下载 runtime。

integration 可向 layout registry 注册自己的 config/runtime/cache 目录，避免框架再次硬编码 MAA。

### P2：命名与保留策略仍可更清楚

`debug/` 实际包含 framework rotating log、每次运行 event JSONL、外部 stdout/stderr、MaaCore capture，不只是调试开关输出。代码层建议使用 `diagnostics_dir` 语义；磁盘第一版可继续叫 `debug/`，减少迁移范围。

`runtime/maa/generated-configs` 和 `run-logs` 是可清理数据，却与可在线更新的 binary/resource 同处一棵集成运行时树。后续若需要不同 retention，再单独拆分，不阻塞当前所有权边界收敛。

## 4. 不应归入 data 的内容

以下内容应随镜像/应用版本发布并保持只读：Python package、前端构建产物、maa-cli schemas、默认配置模板和文档。

`.venv`、`node_modules`、pytest/ruff cache、`.codex` 会话和外部源码也不属于产品 data，它们是开发环境状态，继续单独 ignore。

## 5. 本机目录调整

项目尚未发布，不保留旧布局兼容层或迁移命令。本机数据已在服务停止期间一次性移动到最终目录；以后代码只认当前 `data/` 与 `cache/` 布局。

## 6. 实施顺序

### Phase A：先抽象，不搬数据

1. 新增 `ApplicationPaths`、`FrameworkPaths`、`CachePaths`、`MaaInstallation` 和 `PathResolver`。
2. `create_services()` 接收/构造这些对象。
3. 替换 `MaaRuntime` 在 process/store/diagnostics 中的通用依赖。
4. 加 `--data-dir`/`MAA_AUTO_PANEL_DATA_DIR` 和独立的 `--cache-dir`/`MAA_AUTO_PANEL_CACHE_DIR`。
5. 让 frontend/schema 从只读 application assets 定位。

### Phase B：切换最终布局

1. 默认数据根改为 `<repo>/data`。
2. 所有持久路径使用 data-root-relative reference。
3. download manifest 改为 cache-relative path。
4. 同步 `scripts/maa-env`、tests、README、`docs/maa-runtime.md`、`.gitignore`。

### Phase C：再更新容器方案

1. Compose 为框架数据挂载 `/app/data`，并使用 `/tmp` tmpfs。
2. download cache 独立挂载到 `/app/cache/downloads`，不纳入 data volume。
3. `/home/panel/.android` 使用独立 `adb-state` named volume；不持久化整个 HOME。
4. 应用代码与静态资产保持只读。
5. readiness 检查注册路径可写、runtime binary 可执行。

## 7. 验收标准

- 从任意 cwd 启动，路径均由显式 app/data root 决定。
- 开发默认生成职责明确的 `data/`、`runtime/` 与 `cache/`；不再生成散落的顶层 config/state/history/debug/downloads。
- Web、独立 game CLI、maintenance、scheduler 和 `scripts/maa-env` 使用同一布局。
- 旧数据 dry-run 能列出所有移动与改写；正式迁移后历史详情与日志引用仍可读取。
- 仓库改名或把 data volume 挂到不同宿主路径后，download manifest 仍有效。
- 配置编辑与 schema 校验在安装包/容器中不依赖源码树形态。
- `data`、download cache、ADB state 三类挂载边界明确；删除 download cache 不影响框架状态和后续启动。
- 应用根可设为只读，`/tmp` 使用 tmpfs。
- 测试覆盖路径优先级、跨 cwd、旧 layout 检测、路径逃逸、manifest/history 引用迁移和失败回滚。

## 8. 对现有容器计划的修正

`CONTAINERIZATION_PLAN.md` 当前的多 bind mount 方案是针对旧固定相对路径的兼容方案。完成本审计建议后，应改为“一个框架 data volume + 一个可丢弃 download cache + 一个 ADB credential volume”：

```yaml
environment:
  MAA_AUTO_PANEL_DATA_DIR: /app/data
  MAA_AUTO_PANEL_CACHE_DIR: /app/cache
volumes:
  - /srv/maa-auto-panel/data:/app/data
  - /srv/maa-auto-panel/cache/downloads:/app/cache/downloads
  - adb-state:/home/panel/.android
tmpfs:
  - /tmp:size=256m,mode=1777
```

宿主备份工具仍可针对 `data/config`、`data/state`、`data/history` 等子目录使用不同策略。`cache/downloads` 可直接清空或不备份；`adb-state` 只保存 ADB 授权材料，不承载框架文件。
