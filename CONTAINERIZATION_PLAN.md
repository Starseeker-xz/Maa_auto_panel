# Maa Auto Panel 容器化构筑建议

状态：供下一 session 实施  
来源会话：`2026-07-10_0416-full-project-audit`

## 1. 推荐结论

第一版采用“**单应用容器 + 外部 redroid + 持久化运行时卷**”：

- 一个容器运行 FastAPI、静态前端、scheduler、maa-cli 和容器内 ADB server。
- redroid 继续位于外部 LAN，通过 `192.168.5.151:5555` 访问。
- 不使用 `privileged`、host network、Docker socket 或 USB device mount。
- 保持单实例；不能同时运行裸机 systemd 服务和 Compose 服务。
- `data/runtime/maa` 位于框架 data volume 中，与应用镜像版本解耦。
- maa-cli/MaaCore/resource 继续由面板内维护动作更新；不要求每次 MAA 更新都构建或发布应用镜像。
- 空 runtime 卷只通过显式 bootstrap 安装一个已知可用基线，之后更新结果持续保存在卷中。

这是最符合当前代码路径和单用户维护习惯的方案。应用只在自身代码变化时发布；MAA runtime 按上游节奏独立更新。

## 2. 为什么不把 redroid 一起塞进同一容器

redroid 与控制面生命周期、权限和资源需求不同：

- redroid 需要 Android/container 特有能力，Maa Auto Panel 只需要 TCP ADB。
- 合并会迫使面板容器获得不必要的高权限。
- Android runtime 重启不应带着 WebUI、scheduler 和 history 一起重启。
- 当前目标 redroid 已在 LAN 提供 `5555`，没有合并收益。

未来可以用同一个 Compose 管理两个 service，但仍应是两个容器和两个权限边界。

## 3. 必须遵守的运行约束

### 3.1 单实例

当前 scheduler、RunCoordinator 和 JSON store 都是进程内/单进程模型：

- `replicas` 必须为 1。
- 不做滚动双实例更新。
- 不同时启动 systemd 与 Docker 版本，否则会重复触发 schedule，且两个进程间不会共享 ADB resource lock。
- 切换时顺序：禁用新调度 → 等待/停止当前 run → 停 systemd → 备份数据 → 启 Compose。

### 3.2 TCP ADB

推荐让容器安装 `adb` 并运行自己的 ADB server：

```text
panel container -> bridge/LAN -> 192.168.5.151:5555
```

不推荐连接宿主 ADB server，也不需要：

- `network_mode: host`
- `privileged: true`
- `/dev/bus/usb`
- `ADB_SERVER_SOCKET` 指向宿主

只有未来接入 USB 真机时，才单独设计 USB device/group 权限。

## 4. 第一版目录与持久化

路径管理重构后，框架拥有或运行依赖的数据统一位于 `/app/data`；可丢弃 download cache 与 ADB credential state 使用独立边界：

| 容器路径 | 内容 | 第一版建议 | 备份级别 |
|---|---|---|---|
| `/app/data` | config/state/history/debug/runtime | bind mount | 主持久卷；按子目录采用不同备份策略 |
| `/app/cache/downloads` | APK 与 patch cache | bind mount/独立大盘 | 可删除、通常不备份 |
| `/home/panel/.android` | ADB 客户端 key | named volume | 独立凭据状态，不承载框架数据 |

当前本地规模约为：

- `data/runtime/maa`（迁移前 `runtime/maa`）: 1.3 GB。
- `cache/downloads`（迁移前 `downloads`）: 4.0 GB。
- `data/debug/framework`（迁移前 `debug/framework`）: 106 MB。

因此不要把这些目录放入 Docker build context，也不要直接 COPY 到应用层。

建议宿主数据布局：

```text
/srv/maa-auto-panel/
  data/
    config/
    state/
    history/
    debug/
    runtime/
  cache/
    downloads/
  backups/
```

开发阶段也可以继续 bind 当前仓库目录，生产切换时再迁到 `/srv`。

## 5. 镜像结构

### 5.1 多阶段构建

建议三个 stage：

```text
frontend-builder
  node:22-bookworm-slim
  npm ci
  npm run build

python-builder
  python:3.12-slim-bookworm
  使用 uv --frozen 安装 production dependencies 和项目包

runtime
  python:3.12-slim-bookworm
  安装 adb/git/ca-certificates/tzdata/tini
  COPY Python venv、src/package、frontend/dist
  创建 panel 用户
```

### 5.2 Runtime 系统包

第一版至少需要验证以下 Debian 包：

```text
adb
git
ca-certificates
tzdata
tini
zlib1g
libgcc-s1
libstdc++6
```

不要凭列表认为 MaaCore 一定可运行。构建后必须在最终镜像内执行：

```bash
maa version
maa list
adb version
```

再执行一次真实 redroid screenshot/StartUp smoke test。当前本地 MaaCore library 目录存在 OpenCV SONAME 混合（`.411`/`.412`）迹象，容器验证应以真实加载和执行结果为准。

### 5.3 架构

当前 runtime 是 x86-64 ELF，第一版明确：

```yaml
platform: linux/amd64
```

不要宣称 multi-arch。需要 ARM64 时必须同时准备对应 maa-cli/MaaCore artifacts 并独立测试。

## 6. 第一版 Dockerfile 轮廓

下个 session 可据此生成正式文件，下面仅表示构筑结构：

```dockerfile
FROM node:22-bookworm-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS python-builder
COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv
WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends adb git ca-certificates tzdata tini zlib1g libgcc-s1 libstdc++6 \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:/app/data/runtime/maa/bin:$PATH \
    MAA_AUTO_PANEL_DATA_DIR=/app/data \
    MAA_AUTO_PANEL_CACHE_DIR=/app/cache \
    HOME=/home/panel

WORKDIR /app
COPY --from=python-builder /opt/venv /opt/venv
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist
COPY pyproject.toml README.md ./
COPY docs/maa-cli/ ./docs/maa-cli/
RUN useradd --create-home --no-log-init --uid 10001 panel \
 && mkdir -p data cache/downloads /home/panel/.android \
 && chown -R panel:panel /app /home/panel

USER panel
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["maa-auto-panel", "webui", "--host", "0.0.0.0", "--port", "8000"]
```

venv 必须在 builder 和 runtime 中保持相同绝对路径；否则 console-script shebang 会再次出现仓库重命名后遇到的旧路径问题。完整 `pyproject.toml`、lock 和源码都已复制时使用 `--locked`，让构建在 lock 与项目元数据不一致时失败；`--frozen` 只适合依赖缓存的前置 partial sync。实施时确认 `--no-editable` 确实把项目安装进 `/opt/venv`。另一种可靠方式是先构建 wheel，再按 lock 约束安装到固定 `/opt/venv`。若用 BuildKit cache mount 缓存 uv，设置 `UV_LINK_MODE=copy`，避免跨文件系统 hardlink 警告。`docs/maa-cli/schemas` 也是运行时依赖，`ConfigSchemaValidator` 会直接读取它，不能被 `.dockerignore` 或精简 COPY 遗漏。

固定 UID 创建用户时保留 `--no-log-init`，避免 Debian/Ubuntu 系镜像在某些较大 UID 下生成稀疏 `faillog` 并异常放大镜像层。基础镜像和 uv 镜像至少固定到明确版本；正式发布可进一步记录 digest，并用定期重建吸收安全更新。

## 7. 第一版 Compose 轮廓

```yaml
services:
  panel:
    build:
      context: .
    image: maa-auto-panel:local
    platform: linux/amd64
    restart: unless-stopped
    ports:
      - "192.168.5.15:8000:8000"  # 单用户可信 LAN
      # 宿主地址不固定时可用 "8000:8000"，由 LAN/防火墙承担边界
    environment:
      TZ: Asia/Shanghai
      MAA_AUTO_PANEL_DATA_DIR: /app/data
      MAA_AUTO_PANEL_CACHE_DIR: /app/cache
    volumes:
      - /srv/maa-auto-panel/data:/app/data
      - /srv/maa-auto-panel/cache/downloads:/app/cache/downloads
      - adb-state:/home/panel/.android
    tmpfs:
      - /tmp:size=256m,mode=1777
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    stop_grace_period: 2m

volumes:
  adb-state:
```

首轮 smoke test 可暂时不启用 `read_only: true`。确认所有写路径都在 volume/tmpfs 后，再启用只读 root filesystem。

Dockerfile 已使用 `tini`，Compose 不再同时设置 `init: true`，避免双重 init。若最终去掉 Dockerfile 的 `tini`，再改用 Compose `init: true`，二者保留一个即可。

bind mount 会遮蔽镜像中目标目录原有内容，因此不要把 baseline runtime 先放进 `/app/data` 再指望首次挂载后仍可见。`init-runtime` 应从镜像内只读 seed（例如 `/opt/maa-runtime-seed`）复制，或按固定 URL + checksum 下载到空卷。宿主 bind 目录必须在启动前创建并授予 UID/GID 10001；非 root entrypoint 只能检查权限，不能可靠地替宿主 `chown`。

## 8. `.dockerignore`

至少排除：

```text
.git
.venv
.codex
frontend/node_modules
frontend/dist
data
cache
# 迁移完成前仍排除旧布局
runtime
downloads
debug
state
history
config/maa
config/framework
external
docs/maa-upstream
__pycache__
*.pyc
```

这是必要项；否则 1.3 GB runtime、4 GB downloads 和 external source 会进入 build context。

## 9. Health、启动与停机

### 9.1 新增 health endpoints

建议区分：

- `/api/health`: 进程/event loop 存活，不访问外部网络。
- `/api/ready`: data/config、data/state、data/history 可写、maa binary 存在、scheduler 初始化完成。

Compose healthcheck 使用 Python stdlib 请求 `/api/health`，避免仅为 healthcheck 安装 curl。

healthcheck 应设置足够的 `start_period`，并让 `/api/health` 只反映进程/event loop；redroid 离线、runtime 未初始化等依赖状态放在 `/api/ready`，不能触发 Compose 对健康进程的无意义重启循环。

### 9.2 Entry point 检查

第一版 entrypoint 在启动前检查：

- `/app/data/runtime/maa/bin/maa` 存在且可执行。
- 所有 volume 目录对 UID 10001 可读写。
- config/runtime 版本信息写入启动日志。
- 若 runtime volume 为空，明确失败并提示初始化已知基线，不要静默从网络下载 latest。

### 9.3 优雅停机（已实现）

容器收到 SIGTERM 后必须：

1. Uvicorn 广播 shutdown，SSE 主动结束；5 秒 connection timeout 兜底。
2. scheduler 停止触发，manager/coordinator 拒绝新任务并解除等待。
3. 所有 current run 同时收到 stop，共享等待 60 秒。
4. 剩余任务按完整 process group 强停，共享等待 15 秒。
5. seal retry/run、flush diagnostics，并 join scheduler/run thread。

该链路已通过真实 SSE + SIGTERM 验证；正常退出约 1 秒且 return code 为 0。Compose 继续保留 2 分钟总预算。

## 10. Runtime 更新策略

### 长期模型：应用镜像与 MAA runtime 解耦

- `/app/data/runtime` 随 data 主卷持久化。
- 应用 image tag 只表达 Maa Auto Panel 版本，不绑定 maa-cli/MaaCore 版本。
- maintenance update 保留在 UI 中，但必须先取得 exclusive `runtime:maa` claim，禁止与任何 MAA run 并发。
- 更新下载到 staging 目录，校验上游提供的 checksum/manifest 后再替换目标文件。
- 更新前记录当前 maa-cli/MaaCore/resource 版本并保留最近一份可回退快照；成功运行 `maa version` 后才提交新状态。
- 更新失败时自动回滚；不要让半更新 runtime 成为下一次启动的默认状态。
- cache/generated/MAA state 与已安装 runtime 一起保留在卷中，history/debug 仍使用各自独立卷。

### 空卷 bootstrap

首次部署不应在每次容器启动时追踪 latest。提供显式的一次性命令或 init profile：

```text
docker compose run --rm panel init-runtime
```

它安装项目测试过的基线版本。初始化完成后，正常 `docker compose up` 只检查 runtime 是否存在，不主动联网修改。用户随后可从面板执行正常更新。

### 兼容性提示

应用记录“已测试的 maa-cli/MaaCore 版本范围”，但默认只提示超出范围，不阻止单用户继续更新。只有确认存在破坏性协议变化时，才要求先升级应用。这样大多数 MAA 更新不会带来面板发布负担。

## 11. 网络边界（不引入认证系统）

容器内 `0.0.0.0` 是正常做法，关键是 Compose 如何 publish：

- 可信 LAN：可用 `192.168.5.15:8000:8000`，显式绑定宿主 LAN 地址。
- 若宿主 LAN 地址会变化，也可使用 `8000:8000`，由路由器/宿主防火墙确保端口不暴露到公网。
- 公网部署不属于本项目目标，不为此预装 TLS、认证反代或用户系统。

在“可信内网、单用户”前提下，不实现登录、token、session、RBAC 或用户数据库。若未来产品前提改变，再把认证作为独立需求评估，不提前支付复杂度。

若希望用极低成本防止浏览器访问恶意网页时向内网面板发起跨站写请求，可以让前端对所有 mutating API 统一携带一个固定自定义 header，并由后端拒绝缺少该 header 的写请求。这不是身份认证，不需要账号、密钥或新服务；也可以等容器主流程稳定后再决定是否加入。

## 12. 数据迁移与回退

首次切换建议：

1. 确认没有 active run。
2. `systemctl stop maa-auto-panel-webui.service`，并保持 disabled。
3. 备份当前旧布局的 `config/ state/ history/ runtime/`；`debug/`按空间决定，`downloads/`作为 cache 不进入核心备份。
4. 使用 `rsync -a` 迁入 `/srv/maa-auto-panel/`，保留 symlink 和时间戳。
5. 将目录 owner 调整为容器 UID/GID 10001。
6. 先执行一次性容器验证 `maa version`、`maa list`、`adb connect`。
7. 启动 Compose，验证 health/settings/config read。
8. 手动运行最小 smoke task，再启用 scheduler。

回退：停 Compose，将数据同步回原路径或把 systemd WorkingDirectory 指向备份数据，然后只启动 systemd；任何时候保持单实例。

## 13. 下一 session 的实施顺序

建议严格按以下顺序：

1. 增加 `FrameworkPaths` 的环境变量/显式 root 支持，或先确认 `/app` 固定布局足够作为 v1。
2. application lifespan/graceful shutdown/process group（已完成）。
3. 修复 maintenance runtime exclusive claim。
4. 新增 `/api/health`、`/api/ready`。
5. 新增 `.dockerignore`。
6. 编写 multi-stage Dockerfile。
7. 编写 Compose 与 entrypoint preflight。
8. 在临时数据副本上 build/up，不直接挂生产目录。
9. 验证前端、settings、maa version/list、ADB、手动 smoke、stop/force-stop、scheduler restart recovery。
10. 写入 README 的容器部署、备份、升级、回退说明。

## 14. 验收标准

- image build context 不包含 runtime/downloads/external/local state。
- 容器以非 root UID 运行，`cap_drop: ALL`，无 privileged/host network/Docker socket。
- 能通过 bridge 网络连接 `192.168.5.151:5555`。
- 重启容器后 config/state/history/runtime/download cache 均保留。
- 同一数据目录始终只有一个 panel 实例。
- SIGTERM 能停止 scheduler、收尾 active run，并在 grace period 内退出。
- runtime update 不能与 MAA run 并发。
- healthcheck 不依赖外网和 redroid 在线。
- 完成至少一次手动最小任务和一次 scheduler 触发 smoke test。
- 有可执行的备份、升级与回退步骤。

## 15. 2026-07-11 构筑前复核结论

正式写 Dockerfile 前还需先完成或明确以下门槛：

1. **恢复可复现的 MAA runtime 基线（当前阻断 smoke test）**：当前 `data/runtime/maa` 在宿主和干净 `python:3.12-slim-bookworm` 容器中执行 `maa version` 都失败。已确认 `libMaaCore.so` 需要 `libopencv_world4.so.411`，而 `libMaaAdbControlUnit.so` 需要 `.412`，目录仅有 `.411`。先用完整、带版本和 checksum 的上游 artifact 重建临时 baseline，再判断最终镜像缺少哪些系统库；不要通过伪造 SONAME symlink 掩盖混合更新。
2. **先修 runtime 更新互斥与原子性**：maintenance 仍未取得 exclusive `runtime:maa` claim。容器化会把 runtime 变成长期持久卷，更不能允许运行中覆盖二进制；至少先完成互斥，staging/checksum/rollback 可紧随其后。
3. **实现 health/ready 与 preflight**：这是 Compose healthcheck、首次空卷提示和权限诊断的基础。preflight 以非 root 身份运行，只报告 UID/GID、目录权限、runtime 完整性，不尝试静默修复宿主目录。
4. **确定 bootstrap 供应链**：记录精确 maa-cli/MaaCore/resource 版本、下载 URL、SHA-256 和目标架构；空卷初始化必须显式执行且可重复验证。构建期若未来需要私有 token，使用 BuildKit secret mount，不能放入 `ARG`/`ENV` 或镜像层。
5. **分开验证应用镜像与 runtime**：先用空 data/cache 的应用镜像验证 Python wheel、前端、schema、health、非 root 和只读 rootfs；再挂载修复后的 runtime 做 `maa version/list`、ADB screenshot、最小任务。这样能明确故障属于镜像还是持久化 runtime。
6. **补一份真实部署配置检查**：运行 `docker compose config`，验证 publish 地址确实存在于宿主、`platform: linux/amd64`、`stop_grace_period: 2m`、唯一 init、单实例和 volume 路径；之后才挂临时数据副本执行 `up`。

其余已确认无需提前扩张：不需要 host network、privileged、Docker socket、USB mount、数据库、认证系统或多容器拆分。第一版保持单 panel 容器、外部 TCP redroid 和单实例即可。
