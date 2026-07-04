# Session: 2026-07-04_clone-maa-sources

## Task
克隆 MAA 和 maa-cli 上游源码到 `external/` 目录以供后续开发参考。
分析 MAA GUI 的日志面板组织规律和截图添加规律。

## Actions
1. 创建 `external/` 目录于项目根目录
2. 将 `external/` 加入 `.gitignore`
3. `git clone --depth 1` MaaAssistantArknights → `external/MaaAssistantArknights/`（约 146 MB，10,252 文件）
4. `git clone --depth 1` maa-cli → `external/maa-cli/`（约 360 KB，Rust 项目）
5. 三个并行 subagent 探索：
   - GUI 源码结构分布（`src/MaaWpfGui/` 完整目录树）
   - 日志面板组织规律（LogItemViewModel/LogCardItemViewModel、AddLog 流程、颜色系统、XAML 绑定）
   - 截图机制（C++ 端 screencap → C API AsstGetImage → C# 端缩略图/Peep/调试落盘）
6. 汇总写入 `external/MAA_GUI_ANALYSIS.md`

## Key Findings for Linux MAA

### 日志系统
- 双层模型：LogCardItemViewModel（卡片）包含多个 LogItemViewModel（条目）
- 语义颜色：不设固定 info/warn/error 级别，用语义标签映射颜色（如招募星级、IS 节点）
- 卡片拆分：splitMode 控制 Before/After/Both 边界
- 回调驱动：AsstMsg 枚举 → ProcMsg 分派 → AddLog 统一入口

### 截图系统（重要！）
- **回调只传 JSON 文本，不含图像数据** — 这是刚性约束
- 图像通过独立 API 拉取：AsstGetImage (PNG) / AsstGetImageBgr (raw BGR)
- 三种 GUI 使用场景：日志卡片缩略图（按需）、Peep 实时预览、调试截图落盘
- 唯一内联图像场景：远程控制协议的 base64 HTTP POST

### 对 Linux MAA 的影响
- maa-cli 的 stdout/stderr 不可能包含截图数据
- 如需截图，必须通过 Asst C API 独立拉取，或使用 ADB screencap
- 日志组织可参考卡片+条目的双层模型

## Results
- `external/MaaAssistantArknights/` — MAA 主仓库源码
- `external/maa-cli/` — maa-cli 源码
- `external/MAA_GUI_ANALYSIS.md` — GUI 日志面板与截图机制完整分析
