import { Play, Wrench } from "lucide-react";

import { RunStopButton } from "@/components/RunStopButton";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { STATUS_LABELS } from "@/lib/logs";
import type { RunState, ToolDefinition } from "@/lib/types";

type ToolConfigPaneProps = {
  tool?: ToolDefinition;
  config: Record<string, string>;
  run: RunState;
  busy: boolean;
  onConfigChange: (fieldId: string, value: string) => void;
  onRun: () => void;
  onStop: () => void;
  onForceStop: () => void;
  retryCount: number;
  onRetryCountChange: (value: number) => void;
};

export function ToolConfigPane({ tool, config, run, busy, onConfigChange, onRun, onStop, onForceStop, retryCount, onRetryCountChange }: ToolConfigPaneProps) {
  const active = run.status === "running" || run.status === "stopping";
  const runnable = tool ? requiredFieldsFilled(tool, config) : false;

  return (
    <Card className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-3 overflow-hidden p-3 max-md:p-2">
      <div className="flex items-start justify-between gap-3 max-md:grid max-md:grid-cols-1 max-md:gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Wrench className="size-4 shrink-0 text-muted-foreground" />
          <CardTitle className="truncate">{tool?.title || "小工具"}</CardTitle>
        </div>
        <span className={`status-pill ${run.status}`}>{STATUS_LABELS[run.status] || run.status}</span>
      </div>

      <div className="min-h-0 overflow-auto">
        {tool ? (
          <div className="grid gap-4">
            {tool.fields.map((field) => (
              <label key={field.id} className="grid gap-1.5">
                <span className="text-xs font-medium text-muted-foreground">{field.label}</span>
                <Input
                  className="max-md:h-8 max-md:px-1.5 max-md:text-[11px]"
                  value={config[field.id] || ""}
                  placeholder={field.placeholder || ""}
                  disabled={active}
                  onChange={(event) => onConfigChange(field.id, event.target.value)}
                />
              </label>
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-dashed bg-background px-3 py-8 text-center text-sm text-muted-foreground">暂无工具</div>
        )}
      </div>

      <div className="grid grid-cols-[1fr_1fr_auto] gap-2">
        <Button className="max-md:px-2 max-md:text-xs" onClick={onRun} disabled={busy || active || !runnable}>
          <Play className="size-4" />
          运行
        </Button>
        <RunStopButton className="max-md:px-2 max-md:text-xs" run={run} busy={busy} onStop={onStop} onForceStop={onForceStop} />
        <label className="flex items-center justify-end gap-2">
          <span className="shrink-0 text-right text-[11px] leading-3 text-muted-foreground">重试<br />次数</span>
          <Input className="w-12 px-1 text-center text-sm" type="number" min={1} max={50} aria-label="重试次数" value={retryCount} onChange={(event) => onRetryCountChange(clampRetryCount(event.target.value))} />
        </label>
      </div>
    </Card>
  );
}

function clampRetryCount(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(50, Math.max(1, parsed)) : 1;
}

function requiredFieldsFilled(tool: ToolDefinition, config: Record<string, string>) {
  return tool.fields.every((field) => !field.required || Boolean((config[field.id] || "").trim()));
}
