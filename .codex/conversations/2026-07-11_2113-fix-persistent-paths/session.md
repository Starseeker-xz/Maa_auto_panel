# Session 2026-07-11_2113-fix-persistent-paths

## Scope

- 审计并处理后端 P2：持久路径应表达逻辑根而非部署位置。
- 范围：store、diagnostics、trash、artifact、download manifest。
- 不修改统一进程读取模块及其测试。

## Progress

- 已完成项目状态文件读取。
- 抽样现有 data/cache：diagnostics/history/trash/download manifest 多为无根相对字符串；generated-config artifact 依赖 repo root，在外置 runtime 时会成为绝对路径。
- 新增 `PathReferenceResolver`，统一生成/解析 `framework:...`、`runtime:...`、`downloads:...`，拒绝未知根、错误根、绝对路径与 `..` 逃逸。
- 已迁移新写入路径：diagnostics、retry history index、trash records、MAA generated config/MaaCore artifact、download manifest。
- 新读取 retry history 与 download manifest 经 resolver 解析，不再直接拼接部署根。
- 相关测试：`tests/test_paths_and_migration.py`、`tests/test_run_state_and_diagnostics.py`、`tests/test_run_manager.py`、`tests/test_scheduler_run_manager.py`，16 passed。
- 当前 systemd 服务仍运行旧代码，因此没有在线修改现有 JSON。一次性原子改写脚本位于 `scratch/migrate-logical-path-references.py`，应在停止旧服务后、启动新版前执行。

## Environment effects

- 工作区代码与测试已修改；主 agent 已完成停服、迁移与重启，最终 systemd PID 57764、active。
- 本机 68 个旧 data/cache JSON 已一次性原子改写，旧格式扫描为 0；迁移前备份位于主会话 `2026-07-11_2105-audit-stream-no-newline/scratch/pre-logical-path-migration.tar.gz`。
- 迁移脚本初版错误地对 tuple 调用 `.glob()`，首次执行报错且未改数据；主 agent 修正为逐 root 遍历后成功执行。
