import { ArrowLeft, Info, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { STATUS_LABELS } from "@/lib/logs";
import { formatTimeOfDay } from "@/lib/time";
import type { MaaLogEntry, MaaLogMessage, RunRetry, RunState } from "@/lib/types";
import { cn } from "@/lib/utils";
import React from "react";

type LogPaneProps = {
  run: RunState;
  error: string;
  title?: string;
  emptyText?: string;
  historyRun?: RunState | null;
  onCloseHistory?: () => void;
  hideHeader?: boolean;
  className?: string;
};

const BLOCK_STATUS_LABELS: Record<string, string> = {
  default: "",
  running: "进行中",
  succeeded: "完成",
  failed: "失败",
  stopped: "已停止",
  unknown: "未确认结束",
  unfinished: "未完成",
  warning: "警告"
};

const BLOCK_STATUS_CLASS: Record<string, string> = {
  default: "text-muted-foreground",
  running: "text-sky-600 dark:text-sky-300",
  succeeded: "text-emerald-600 dark:text-emerald-300",
  failed: "text-destructive",
  stopped: "text-amber-600 dark:text-amber-300",
  unknown: "text-muted-foreground",
  unfinished: "text-amber-600 dark:text-amber-300",
  warning: "text-amber-600 dark:text-amber-300"
};

const BLOCK_PANEL_CLASS: Record<string, string> = {
  default: "border-border bg-background shadow-sm",
  running: "border-primary/70 bg-background shadow-sm shadow-primary/10",
  succeeded: "border-border bg-background shadow-sm",
  failed: "border-amber-500 bg-amber-50/40 shadow-sm shadow-amber-500/10 dark:bg-amber-950/10",
  stopped: "border-amber-500 bg-amber-50/40 shadow-sm shadow-amber-500/10 dark:bg-amber-950/10",
  unknown: "border-border bg-background shadow-sm",
  unfinished: "border-amber-500 bg-amber-50/40 shadow-sm shadow-amber-500/10 dark:bg-amber-950/10",
  warning: "border-amber-500 bg-amber-50/40 shadow-sm shadow-amber-500/10 dark:bg-amber-950/10"
};

const MESSAGE_TONE_CLASS: Record<string, string> = {
  default: "text-muted-foreground",
  info: "text-muted-foreground",
  success: "text-emerald-600 dark:text-emerald-300",
  warning: "text-amber-600 dark:text-amber-300",
  danger: "text-destructive",
  theme: "text-primary"
};

export function LogPane({ run, error, title = "日志", emptyText = "等待 maa-cli info 日志...", historyRun = null, onCloseHistory, hideHeader = false, className }: LogPaneProps) {
  const viewingHistory = Boolean(historyRun);
  const visibleRun = historyRun || run;
  const entries = normalizeEntries(visibleRun);
  const details = runDetails(visibleRun, entries);
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const viewportRef = React.useRef<HTMLDivElement>(null);
  const followTailRef = React.useRef(true);
  const currentRunActive = isRunActive(run);

  React.useEffect(() => {
    followTailRef.current = true;
    setDetailsOpen(false);
  }, [visibleRun.id, viewingHistory]);

  React.useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !followTailRef.current) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, [entries.length, visibleRun.id, visibleRun.stream_version, visibleRun.updated_at]);

  function handleScroll(event: React.UIEvent<HTMLDivElement>) {
    const viewport = event.currentTarget;
    const distanceFromBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
    followTailRef.current = distanceFromBottom < 48;
  }

  return (
    <Card
      className={cn(
        "relative grid min-h-0 gap-0 overflow-hidden p-0",
        hideHeader ? "grid-rows-[minmax(0,1fr)_auto]" : "grid-rows-[auto_minmax(0,1fr)_auto] max-xl:col-span-2 max-md:col-span-1 max-xl:min-h-80",
        className
      )}
    >
      {hideHeader ? null : (
        <CardHeader className="grid-rows-none gap-0 border-b px-3 py-2">
          <div className="flex min-h-12 items-center justify-between gap-3">
            <div className="grid min-w-0 gap-1">
              <CardTitle className="truncate">{title}</CardTitle>
              <span className={`status-pill ${viewingHistory ? "history" : visibleRun.status}`}>{viewingHistory ? STATUS_LABELS.history : STATUS_LABELS[visibleRun.status] || visibleRun.status}</span>
            </div>
            {viewingHistory && onCloseHistory ? (
              <Button type="button" variant="outline" size="sm" className="h-7 shrink-0 px-2 text-xs" onClick={onCloseHistory}>
                {currentRunActive ? <ArrowLeft className="size-3.5" /> : <X className="size-3.5" />}
                {currentRunActive ? "返回当前日志" : "关闭历史日志"}
              </Button>
            ) : null}
          </div>
        </CardHeader>
      )}
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
      {error ? <CardContent className="border-t py-2 pl-12 pr-2 text-right text-xs text-destructive break-anywhere">{error}</CardContent> : null}
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
  const retries = run.retries || [];
  if ((run.max_retries || 1) <= 1) {
    return retries.flatMap((retry) => retry.log_entries || []);
  }
  return retries.flatMap((retry) => [retryMarkerEntry(retry), ...(retry.log_entries || [])]);
}

function runDetails(run: RunState, entries: MaaLogEntry[]): RunDetailItem[] {
  const details: RunDetailItem[] = [];
  if (run.id) details.push({ label: "Run ID", value: run.id });
  const scheduleName = stringMetadata(run, "schedule_name");
  const entryName = stringMetadata(run, "entry_name");
  if (scheduleName) details.push({ label: "Schedule", value: scheduleName });
  if (entryName) details.push({ label: "Entry", value: entryName });

  for (const [label, path] of Object.entries(run.log_files || {})) {
    if (path) details.push({ label: `${label} log`, value: path });
  }
  for (const [label, value] of artifactDetails(run.artifacts)) {
    details.push({ label, value });
  }
  for (const retry of run.retries || []) {
    for (const [label, value] of artifactDetails(retry.artifacts)) {
      details.push({ label: `retry ${retry.retry_index} ${label}`, value });
    }
  }

  const selections = selectionDetails(entries);
  for (const [label, values] of selections) {
    details.push({ label, value: values.join(" / ") });
  }
  return details;
}

function stringMetadata(run: RunState, key: string): string {
  const value = run.metadata?.[key];
  return typeof value === "string" ? value : "";
}

function artifactDetails(artifacts: Record<string, unknown> | undefined): Array<[string, string]> {
  return Object.entries(artifacts || {})
    .map(([key, value]) => [artifactLabel(key), artifactValue(value)] as [string, string])
    .filter(([, value]) => Boolean(value));
}

function artifactLabel(key: string) {
  return key.replace(/_/g, " ");
}

function artifactValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  return JSON.stringify(value) || String(value);
}

function retryMarkerEntry(retry: RunRetry): MaaLogEntry {
  return {
    type: "block",
    id: `${retry.id}-marker`,
    source: "framework:event",
    kind: "retry",
    title: `第 ${retry.retry_index} 次重试`,
    status: retry.closed ? "default" : "running",
    time: retry.started_at,
    opened_at: retry.started_at,
    sealed_at: retry.ended_at,
    updated_at: retry.updated_at,
    closed: retry.closed ?? false,
    tone: retry.retry_index === 1 ? "info" : "warning",
    messages: [
      {
        text: `第 ${retry.retry_index} 次重试`,
        tone: retry.retry_index === 1 ? "info" : "warning"
      }
    ],
    lines: []
  };
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
  const time = entry.time || entry.sealed_at || entry.opened_at || entry.updated_at || undefined;
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
  return <div className="pt-1.5 text-right font-mono text-xs leading-5 text-muted-foreground tabular-nums">{formatTimeOfDay(time)}</div>;
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
  return [];
}

function isRunActive(run: RunState): boolean {
  return run.status === "running" || run.status === "stopping";
}
