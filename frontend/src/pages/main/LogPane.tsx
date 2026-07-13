import { ArrowLeft, Info, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { STATUS_LABELS } from "@/lib/logs";
import type { MaaLogEntry, MaaLogMessage, RunState } from "@/lib/types";
import { cn } from "@/lib/utils";
import { RetryLogList } from "@/pages/main/RetryLogList";
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

export function LogPane({ run, error, title = "日志", emptyText = "等待 maa-cli info 日志...", historyRun = null, onCloseHistory, hideHeader = false, className }: LogPaneProps) {
  const viewingHistory = Boolean(historyRun);
  const visibleRun = historyRun || run;
  const entries = (visibleRun.retries || []).flatMap((retry) => retry.log_entries || []);
  const hasVisibleContent = (visibleRun.max_retries || 1) > 1 ? Boolean(visibleRun.retries?.length) : Boolean(entries.length);
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
        {hasVisibleContent ? (
          <RetryLogList key={`${viewingHistory ? "history" : "live"}:${visibleRun.id || "idle"}`} run={visibleRun} />
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

function isRunActive(run: RunState): boolean {
  return run.status === "running" || run.status === "stopping";
}
