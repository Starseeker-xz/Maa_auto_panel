import * as React from "react";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { STATUS_LABELS } from "@/lib/logs";
import { formatTimeOfDay } from "@/lib/time";
import type { MaaLogEntry, MaaLogMessage, RunRetry, RunState } from "@/lib/types";
import { cn } from "@/lib/utils";

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

const RETRY_PANEL_CLASS: Record<string, string> = {
  running: "border-primary/70 bg-primary/[0.045]",
  succeeded: "border-emerald-500/60 bg-emerald-500/[0.035]",
  failed: "border-destructive/70 bg-destructive/[0.035]",
  stopped: "border-amber-500/70 bg-amber-500/[0.045]",
  soft_failed: "border-amber-500/70 bg-amber-500/[0.045]",
  skipped: "border-border bg-muted/20",
  default: "border-border bg-muted/15"
};

const MESSAGE_TONE_CLASS: Record<string, string> = {
  default: "text-muted-foreground",
  info: "text-muted-foreground",
  success: "text-emerald-600 dark:text-emerald-300",
  warning: "text-amber-600 dark:text-amber-300",
  danger: "text-destructive",
  theme: "text-primary"
};

export function RetryLogList({ run }: { run: RunState }) {
  const retries = run.retries || [];
  if ((run.max_retries || 1) <= 1) {
    return <LogEntryList entries={retries.flatMap((retry) => retry.log_entries || [])} />;
  }
  return <RetryAccordion retries={retries} maxRetries={run.max_retries || 1} />;
}

function RetryAccordion({ retries, maxRetries }: { retries: RunRetry[]; maxRetries: number }) {
  const [openRetryId, setOpenRetryId] = React.useState(() => retries[retries.length - 1]?.id || "");
  const knownRetryIds = React.useRef(new Set(retries.map((retry) => retry.id)));
  const retryIdsKey = retries.map((retry) => retry.id).join("\u0000");

  React.useLayoutEffect(() => {
    const added = retries.filter((retry) => !knownRetryIds.current.has(retry.id));
    knownRetryIds.current = new Set(retries.map((retry) => retry.id));
    if (added.length) setOpenRetryId(added[added.length - 1]?.id || "");
  }, [retryIdsKey]);

  return (
    <Accordion type="single" collapsible value={openRetryId} onValueChange={setOpenRetryId} className="grid gap-1.5">
      {retries.map((retry) => (
        <RetryItem key={retry.id} retry={retry} maxRetries={maxRetries} />
      ))}
    </Accordion>
  );
}

function RetryItem({ retry, maxRetries }: { retry: RunRetry; maxRetries: number }) {
  const status = retry.status || "default";
  const panelClass = RETRY_PANEL_CLASS[status] || RETRY_PANEL_CLASS.default;
  const summaryMessages = retry.summary_messages || [];

  return (
    <AccordionItem value={retry.id}>
      <div className={cn("overflow-hidden rounded-md border-2", panelClass)}>
        <AccordionTrigger className="min-h-10 px-3 py-2 hover:bg-accent/35">
          <div className="flex min-w-0 items-center gap-2">
            <span className={cn("status-pill shrink-0", status)}>{STATUS_LABELS[status] || status}</span>
            <span className="truncate text-xs font-medium">重试 {retry.retry_index}/{maxRetries}</span>
          </div>
        </AccordionTrigger>
        {summaryMessages.length ? (
          <div className="grid gap-0.5 border-t border-border/70 px-3 py-1.5 text-xs leading-5">
            {summaryMessages.map((message, index) => (
              <MessageContent key={index} message={message} />
            ))}
          </div>
        ) : null}
      </div>
      <AccordionContent className="pt-1.5">
        <LogEntryList entries={retry.log_entries || []} />
      </AccordionContent>
    </AccordionItem>
  );
}

function LogEntryList({ entries }: { entries: MaaLogEntry[] }) {
  return (
    <div className="grid gap-1.5">
      {entries.map((entry) => (
        <LogEntryView key={entry.id} entry={entry} />
      ))}
    </div>
  );
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
        <img src={message.image.src} alt={message.image.alt || ""} width={message.image.width} height={message.image.height} className="mt-1 max-h-28 max-w-full rounded border object-contain" />
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
  return entry.lines.length ? entry.lines.map((line) => ({ text: line, tone: entry.tone || "default" })) : [];
}
