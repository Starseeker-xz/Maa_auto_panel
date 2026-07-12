# Session 2026-07-12_0216-fix-scrcpy-url

## 目标

- 排查并修正 scrcpy 启动 URL 中 `request_id` 的校验失败问题。
- 确认协议文档与前端生成逻辑一致。

## 结论

- `request_id` 的问题不在 URL 结构本身，而在前端兜底生成逻辑：`crypto.randomUUID()` 不可用时，旧实现会回退到时间戳+随机片段，不能通过 UUID 校验。
- 已把兜底改成 canonical UUID v4 生成，并同步更新协议文档说明。

## 验证

- `cd frontend && npm run build`：通过。
