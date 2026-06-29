import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { STATUS_LABELS } from "@/lib/logs";
import type { RunState } from "@/lib/types";

type LogPaneProps = {
  run: RunState;
  logText: string;
  error: string;
};

export function LogPane({ run, logText, error }: LogPaneProps) {
  return (
    <Card className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden p-0 max-xl:col-span-2 max-md:col-span-1 max-xl:min-h-80">
      <CardHeader className="border-b p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="grid gap-1">
            <CardTitle>日志</CardTitle>
            <span className={`status-pill ${run.status}`}>{STATUS_LABELS[run.status] || run.status}</span>
          </div>
          <div className="grid max-w-56 justify-items-end gap-1 text-xs text-muted-foreground">
            <span>info</span>
            {run.log_file ? <span className="break-anywhere text-right">{run.log_file}</span> : null}
          </div>
        </div>
      </CardHeader>
      <pre className="m-0 overflow-auto bg-card p-3 font-mono text-xs leading-6 text-muted-foreground whitespace-pre-wrap">
        {logText || "等待 maa-cli info 日志..."}
      </pre>
      {error ? <CardContent className="border-t p-2 text-xs text-destructive break-anywhere">{error}</CardContent> : null}
    </Card>
  );
}
