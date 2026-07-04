import { Info } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { STATUS_LABELS } from "@/lib/logs";
import type { MaaLogEntry, MaaLogMessage, RunState } from "@/lib/types";
import React from "react";

type LogPaneProps = {
  run: RunState;
  error: string;
  title?: string;
  emptyText?: string;
};

const BLOCK_STATUS_LABELS: Record<string, string> = {
  default: "",
  running: "进行中",
  succeeded: "完成",
  failed: "失败",
  stopped: "已停止",
  unknown: "未确认结束",
  warning: "警告"
};

const BLOCK_STATUS_CLASS: Record<string, string> = {
  default: "text-muted-foreground",
  running: "text-sky-600 dark:text-sky-300",
  succeeded: "text-emerald-600 dark:text-emerald-300",
  failed: "text-destructive",
  stopped: "text-amber-600 dark:text-amber-300",
  unknown: "text-muted-foreground",
  warning: "text-amber-600 dark:text-amber-300"
};

const BLOCK_PANEL_CLASS: Record<string, string> = {
  default: "border-border bg-background shadow-sm",
  running: "border-primary/70 bg-background shadow-sm shadow-primary/10",
  succeeded: "border-border bg-background shadow-sm",
  failed: "border-amber-500 bg-amber-50/40 shadow-sm shadow-amber-500/10 dark:bg-amber-950/10",
  stopped: "border-amber-500 bg-amber-50/40 shadow-sm shadow-amber-500/10 dark:bg-amber-950/10",
  unknown: "border-border bg-background shadow-sm",
  warning: "border-amber-500 bg-amber-50/40 shadow-sm shadow-amber-500/10 dark:bg-amber-950/10"
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
  const details = runDetails(run, entries);
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const viewportRef = React.useRef<HTMLDivElement>(null);
  const followTailRef = React.useRef(true);

  React.useEffect(() => {
    followTailRef.current = true;
    setDetailsOpen(false);
  }, [run.id]);

  React.useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !followTailRef.current) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, [entries.length, run.id, run.stream_version, run.updated_at]);

  function handleScroll(event: React.UIEvent<HTMLDivElement>) {
    const viewport = event.currentTarget;
    const distanceFromBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
    followTailRef.current = distanceFromBottom < 48;
  }

  return (
    <Card className="relative grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-0 overflow-hidden p-0 max-xl:col-span-2 max-md:col-span-1 max-xl:min-h-80">
      <CardHeader className="border-b px-3 py-2.5">
        <div className="flex items-start justify-between gap-3">
          <div className="grid gap-1">
            <CardTitle>{title}</CardTitle>
            <span className={`status-pill ${run.status}`}>{STATUS_LABELS[run.status] || run.status}</span>
          </div>
        </div>
      </CardHeader>
      <div ref={viewportRef} onScroll={handleScroll} className="m-0 min-h-0 overflow-auto bg-card p-3">
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
      {detailsOpen ? <RunDetailsPanel details={details} /> : null}
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="absolute bottom-2 left-2 z-20 size-7 rounded-full bg-background/95 text-muted-foreground shadow-md hover:text-foreground"
        aria-label="本次运行详情"
        aria-expanded={detailsOpen}
        onClick={() => setDetailsOpen((current) => !current)}
      >
        <Info className="size-3.5" />
      </Button>
      {error ? <CardContent className="border-t p-2 text-xs text-destructive break-anywhere">{error}</CardContent> : null}
    </Card>
  );
}

type RunDetailItem = {
  label: string;
  value: string;
};

function RunDetailsPanel({ details }: { details: RunDetailItem[] }) {
  return (
    <div className="absolute bottom-10 left-2 z-20 grid max-h-[45%] w-[min(28rem,calc(100%-1rem))] gap-2 overflow-auto rounded-md border bg-popover p-3 text-xs text-popover-foreground shadow-lg">
      <div className="font-medium">本次运行详情</div>
      {details.length ? (
        <div className="grid gap-2">
          {details.map((item) => (
            <div key={`${item.label}:${item.value}`} className="grid gap-0.5">
              <div className="text-[10px] uppercase tracking-normal text-muted-foreground">{item.label}</div>
              <div className="break-anywhere leading-5">{item.value}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-muted-foreground">暂无详细信息</div>
      )}
    </div>
  );
}

function normalizeEntries(run: RunState): MaaLogEntry[] {
  return run.log_entries || [];
}

function runDetails(run: RunState, entries: MaaLogEntry[]): RunDetailItem[] {
  const details: RunDetailItem[] = [];
  if (run.id) details.push({ label: "Run ID", value: run.id });
  if (run.schedule_name) details.push({ label: "Schedule", value: run.schedule_name });
  if (run.entry_name) details.push({ label: "Entry", value: run.entry_name });

  for (const [label, path] of Object.entries(run.log_files || {})) {
    if (path) details.push({ label: `${label} log`, value: path });
  }
  if (!run.log_files?.stdout && run.log_file) {
    details.push({ label: "log", value: run.log_file });
  }

  const selections = selectionDetails(entries);
  for (const [label, values] of selections) {
    details.push({ label, value: values.join(" / ") });
  }
  return details;
}

function selectionDetails(entries: MaaLogEntry[]) {
  const selections = new Map<string, string[]>();
  const prefixes: Array<[string, string]> = [
    ["选择战斗关卡:", "战斗关卡"],
    ["选择基建计划:", "基建计划"]
  ];

  for (const message of flattenMessages(entries)) {
    for (const [prefix, label] of prefixes) {
      if (!message.text.startsWith(prefix)) continue;
      const value = message.text.slice(prefix.length).trim();
      if (!value) continue;
      const values = selections.get(label) || [];
      if (!values.includes(value)) values.push(value);
      selections.set(label, values);
    }
  }
  return selections;
}

function flattenMessages(entries: MaaLogEntry[]): MaaLogMessage[] {
  const messages: MaaLogMessage[] = [];
  for (const entry of entries) {
    if (entry.messages?.length) messages.push(...entry.messages);
  }
  return messages;
}

function LogEntryView({ entry }: { entry: MaaLogEntry }) {
  const status = entry.status || "default";
  const title = status === "default" ? "" : blockTitle(entry);
  const isCompact = !title && status === "default";
  const statusClass = BLOCK_STATUS_CLASS[status] || BLOCK_STATUS_CLASS.default;
  const panelClass = BLOCK_PANEL_CLASS[status] || BLOCK_PANEL_CLASS.default;
  const time = entry.ended_at || entry.started_at || entry.time || undefined;
  const messages = entry.messages?.length ? entry.messages : fallbackMessages(entry);

  return (
    <div className="grid grid-cols-[3.75rem_minmax(0,1fr)] items-start gap-2">
      <TimeStamp time={time} />
      <div className={isCompact ? "rounded-md border bg-background px-3 py-1.5 text-xs leading-5 shadow-sm" : `rounded-md border-2 px-3 py-2 text-xs leading-5 transition-colors ${panelClass}`}>
        {!isCompact && title ? <div className={`font-medium ${statusClass}`}>{title}</div> : null}
        <div className={isCompact ? "grid gap-0.5" : "mt-1 grid gap-0.5"}>
          {messages.map((message, index) => (
            <MessageContent key={index} message={message} />
          ))}
        </div>
      </div>
    </div>
  );
}

function TimeStamp({ time }: { time?: string | null }) {
  return <div className="pt-1.5 text-right font-mono text-xs leading-5 text-muted-foreground tabular-nums">{time || ""}</div>;
}

function MessageContent({ message }: { message: MaaLogMessage }) {
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

function blockTitle(entry: MaaLogEntry) {
  const status = entry.status || "default";
  const statusLabel = BLOCK_STATUS_LABELS[status] || status;
  const title = entry.name || entry.title || "";
  if (entry.panel_kind === "task" || entry.task_id || entry.source_name) {
    return `任务 ${title} ${statusLabel}`.trim();
  }
  return title || entry.kind;
}

function fallbackMessages(entry: MaaLogEntry): MaaLogMessage[] {
  if (entry.lines.length) {
    return entry.lines.map((line) => ({ text: line, tone: entry.tone || "default" }));
  }
  if (entry.title) return [{ text: entry.title, tone: entry.tone || "default" }];
  return [];
}
