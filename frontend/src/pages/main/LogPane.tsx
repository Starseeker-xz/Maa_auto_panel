import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { STATUS_LABELS } from "@/lib/logs";
import type { MaaLogEntry, MaaLogLineEntry, MaaLogMessage, MaaLogSummaryEntry, MaaLogTaskEntry, RunState } from "@/lib/types";

type LogPaneProps = {
  run: RunState;
  error: string;
  title?: string;
  emptyText?: string;
};

const TASK_STATUS_LABELS: Record<string, string> = {
  running: "进行中",
  succeeded: "完成",
  failed: "失败",
  stopped: "已停止",
  unknown: "未确认结束"
};

const TASK_STATUS_CLASS: Record<string, string> = {
  running: "text-sky-600 dark:text-sky-300",
  succeeded: "text-emerald-600 dark:text-emerald-300",
  failed: "text-destructive",
  stopped: "text-amber-600 dark:text-amber-300",
  unknown: "text-muted-foreground"
};

const TASK_PANEL_CLASS: Record<string, string> = {
  running: "border-primary/70 bg-background shadow-sm shadow-primary/10",
  succeeded: "border-border bg-background shadow-sm",
  failed: "border-amber-500 bg-amber-50/40 shadow-sm shadow-amber-500/10 dark:bg-amber-950/10",
  stopped: "border-amber-500 bg-amber-50/40 shadow-sm shadow-amber-500/10 dark:bg-amber-950/10",
  unknown: "border-border bg-background shadow-sm"
};

const MESSAGE_TONE_CLASS: Record<string, string> = {
  default: "text-muted-foreground",
  info: "text-muted-foreground",
  success: "text-emerald-600 dark:text-emerald-300",
  warning: "text-amber-600 dark:text-amber-300",
  danger: "text-destructive"
};

export function LogPane({ run, error, title = "日志", emptyText = "等待 maa-cli info 日志..." }: LogPaneProps) {
  const entries = normalizeEntries(run);

  return (
    <Card className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-0 overflow-hidden p-0 max-xl:col-span-2 max-md:col-span-1 max-xl:min-h-80">
      <CardHeader className="border-b px-3 py-2.5">
        <div className="flex items-start justify-between gap-3">
          <div className="grid gap-1">
            <CardTitle>{title}</CardTitle>
            <span className={`status-pill ${run.status}`}>{STATUS_LABELS[run.status] || run.status}</span>
          </div>
          <div className="grid max-w-56 justify-items-end gap-1 text-xs text-muted-foreground">
            <span>info</span>
            {run.log_file ? <span className="break-anywhere text-right">{run.log_file}</span> : null}
          </div>
        </div>
      </CardHeader>
      <div className="m-0 min-h-0 overflow-auto bg-card p-3">
        {entries.length ? (
          <div className="grid gap-1.5">
            {entries.map((entry, index) => (
              <LogEntryView key={index} entry={entry} />
            ))}
          </div>
        ) : (
          <div className="rounded-md border bg-background px-3 py-2 text-xs text-muted-foreground">{emptyText}</div>
        )}
      </div>
      {error ? <CardContent className="border-t p-2 text-xs text-destructive break-anywhere">{error}</CardContent> : null}
    </Card>
  );
}

function normalizeEntries(run: RunState): MaaLogEntry[] {
  if (run.log_entries?.length) return run.log_entries;
  const output = run.output || [];
  return output
    .join("")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((text) => ({ type: "line", text, tone: "default" }));
}

function LogEntryView({ entry }: { entry: MaaLogEntry }) {
  if (entry.type === "task") return <TaskEntryView entry={entry} />;
  if (entry.type === "summary") return <SummaryEntryView entry={entry} />;
  return <LineEntryView entry={entry} />;
}

function LineEntryView({ entry }: { entry: MaaLogLineEntry }) {
  return (
    <div className="grid grid-cols-[3.75rem_minmax(0,1fr)] items-start gap-2">
      <TimeStamp time={entry.time} />
      <div className="rounded-md border bg-background px-3 py-1.5 text-xs leading-5 shadow-sm">
        <MessageContent message={entry} />
      </div>
    </div>
  );
}

function TaskEntryView({ entry }: { entry: MaaLogTaskEntry }) {
  const statusClass = TASK_STATUS_CLASS[entry.status] || TASK_STATUS_CLASS.unknown;
  const panelClass = TASK_PANEL_CLASS[entry.status] || TASK_PANEL_CLASS.unknown;
  const title = `任务 ${entry.name} ${TASK_STATUS_LABELS[entry.status] || entry.status}`;
  const time = entry.ended_at || entry.started_at || undefined;

  return (
    <div className="grid grid-cols-[3.75rem_minmax(0,1fr)] items-start gap-2">
      <TimeStamp time={time} />
      <div className={`rounded-md border-2 px-3 py-2 text-xs leading-5 transition-colors ${panelClass}`}>
        <div className={`font-medium ${statusClass}`}>{title}</div>
        {entry.messages?.length ? (
          <div className="mt-1 grid gap-0.5">
            {entry.messages.map((message, index) => (
              <MessageContent key={index} message={message} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SummaryEntryView({ entry }: { entry: MaaLogSummaryEntry }) {
  const statusClass = TASK_STATUS_CLASS[entry.status] || TASK_STATUS_CLASS.unknown;
  const panelClass = TASK_PANEL_CLASS[entry.status] || TASK_PANEL_CLASS.unknown;

  return (
    <div className="grid grid-cols-[3.75rem_minmax(0,1fr)] items-start gap-2">
      <TimeStamp />
      <div className={`rounded-md border-2 px-3 py-2 text-xs leading-5 transition-colors ${panelClass}`}>
        <div className={`font-medium ${statusClass}`}>{entry.title || "运行摘要"}</div>
        {entry.messages?.length ? (
          <div className="mt-1 grid gap-0.5">
            {entry.messages.map((message, index) => (
              <MessageContent key={index} message={message} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function TimeStamp({ time }: { time?: string | null }) {
  return <div className="pt-1.5 text-right font-mono text-xs leading-5 text-muted-foreground tabular-nums">{time || ""}</div>;
}

function MessageContent({ message }: { message: MaaLogMessage | MaaLogLineEntry }) {
  const toneClass = MESSAGE_TONE_CLASS[message.tone || "default"] || MESSAGE_TONE_CLASS.default;

  return (
    <div className={`break-anywhere ${toneClass}`}>
      {message.segments?.length ? (
        message.segments.map((segment, index) => (
          <span key={index} className={`${MESSAGE_TONE_CLASS[segment.tone || message.tone || "default"] || toneClass} ${segment.strong ? "font-medium" : ""}`}>
            {segment.text}
          </span>
        ))
      ) : (
        <span>{message.text}</span>
      )}
      {message.image ? (
        <img
          src={message.image.src}
          alt={message.image.alt || ""}
          width={message.image.width}
          height={message.image.height}
          className="mt-1 max-h-28 max-w-full rounded border object-contain"
        />
      ) : null}
    </div>
  );
}
