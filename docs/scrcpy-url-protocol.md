# scrcpy-tool URL 协议

本文定义独立项目 `scrcpy-tool` 对外提供的通用 Scrcpy 启动 URL 协议。任何网页或本地应用均可作为调用方；Maa Auto Panel 只是其中一个使用者，不属于协议命名或实现边界。

## URL 定义

```text
scrcpy-tool://launch/v1?device=<percent-encoded-device>&arg=<percent-encoded-argument>&arg=<percent-encoded-argument>&request_id=<uuid>
```

- scheme 固定为 `scrcpy-tool`，由独立的 scrcpy-tool 安装程序注册。
- authority 固定为 `launch`，表示启动一次 Scrcpy 会话。
- path 固定为 `/v1`；不识别的版本必须明确拒绝，不能静默按其他版本执行。
- `device` 必填且只能出现一次，对应面板默认 profile 的 `connection.address`。
- `arg` 可出现零到多次。每个值表示一个完整 argv 元素，顺序与 URL 中一致；不能把多个参数拼成一个 shell 字符串。
- `request_id` 必填，由面板为每次点击生成标准 UUID v4 形式字符串，仅用于日志关联和重复请求诊断，不作为鉴权凭据。
- 所有 query value 使用 UTF-8 后进行标准 percent-encoding。

示例：

```text
scrcpy-tool://launch/v1?device=192.168.1.20%3A5555&arg=--max-size&arg=1920&arg=--turn-screen-off&request_id=6cefd25a-31ea-4f15-9da7-232ce43d910d
```

等价的 Scrcpy argv：

```text
scrcpy --serial 192.168.1.20:5555 --max-size 1920 --turn-screen-off
```

## 启动器实现要求

1. scrcpy-tool 安装程序应为当前用户注册 `scrcpy-tool` URL scheme，并提供卸载时清理注册项的能力。Windows 为首要目标；若支持 Linux/macOS，应保持完全相同的 URL 语义。
2. URL 解析必须使用平台或语言的 URI parser。严格校验 scheme、authority、path、参数基数和 UTF-8 编码；拒绝 fragment、userinfo、未知的非空 authority/path 及畸形 percent-encoding。
3. 启动器拥有本机 `scrcpy` 与 `adb` 可执行文件的定位配置。面板不会传递服务端 `connection.adb_path`，因为该路径不属于浏览器所在电脑。
4. 进程必须通过 argv 数组启动，禁止 shell、`cmd /c`、PowerShell command string 或字符串拼接执行。
5. `device` 去除首尾空白后必须非空，并拒绝 NUL、CR、LF 和其他控制字符。启动 Scrcpy 时始终由启动器生成 `--serial <device>`；来自 `arg` 的值不得再次设置或覆盖设备选择参数。
6. `arg` 应按明确 allowlist 校验。第一版至少支持面板计划暴露的 Scrcpy 参数；拒绝可执行任意程序、加载任意脚本/配置、覆盖 serial/selector 或改变启动器自身行为的参数。未知参数应显示清晰错误，而非忽略。
7. 建议限制完整 URL 不超过 8192 字节、`arg` 不超过 64 个、单个值不超过 1024 字节，并在解析后再次检查限制。
8. 对形如 `host:port` 的 TCP 设备，启动器可先用其本机 adb 执行有超时的连接检查，再启动 Scrcpy；失败时应显示设备地址和可操作的错误信息。不得把 URL 内容写入 shell。
9. 启动器应快速返回 URL handler 进程，实际 Scrcpy 生命周期由独立进程管理。重复点击的策略必须确定且可测试：建议同一 device 已有窗口时激活该窗口，不同 device 可分别启动。
10. 每次请求记录时间、`request_id`、设备、校验结果和启动结果。日志不得记录未来可能加入的敏感值；不应提供网络监听端口，也不需要接受面板回调。
11. 错误需要通过本机 GUI 通知或对话框呈现，包括协议版本不支持、参数非法、找不到可执行文件、ADB 连接失败和 Scrcpy 启动失败。浏览器无法可靠读取自定义 scheme 的执行结果，因此不能依赖网页接收成功响应。

## 面板侧约定

- 通用入口读取已保存的 `default` profile：`connection.address` 生成 `device`。
- Maa Auto Panel 当前提供结构化的通用视频设置：`framework.scrcpy.video_bit_rate_mbps`（默认 100）和 `framework.scrcpy.max_fps`（默认 60），分别生成 `--video-bit-rate=<value>M` 与 `--max-fps=<value>` 两个 `arg`。不允许用户输入整段命令行文本。
- 生成 URL 前面板也执行基础校验；地址缺失时不触发 scheme，而是引导用户前往设备设置。
- 页面若以后提供特定设备上下文，只替换 `device`；通用 Scrcpy 参数仍来自同一设置。第一版不在 URL 中传 token、文件路径、回调 URL 或任意命令。

## 验收用例

- 包含 TCP 地址、USB serial、空参数、中文/空格参数的 URL 均能保持 argv 边界。
- 缺少/重复 `device`、错误版本、畸形编码、控制字符、过长 URL、未知或禁止的 `arg` 均被拒绝且不启动进程。
- `arg=--serial`、`arg=-s` 等设备覆盖方式无法绕过 `device`。
- 参数中包含 `&`、引号、反引号、`$()`、`%COMSPEC%` 等内容时不会发生 shell 执行。
- 安装、升级、卸载后 scheme 注册状态正确；浏览器首次调用的系统确认流程有用户文档。
