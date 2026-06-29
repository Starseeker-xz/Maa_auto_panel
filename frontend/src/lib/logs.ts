export const STATUS_LABELS: Record<string, string> = {
  idle: "空闲",
  running: "运行中",
  stopping: "停止中",
  succeeded: "已完成",
  failed: "失败",
  timeout: "超时"
};

export function translateLogLine(line: string): string {
  return line;
}
