import { Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { RunState } from "@/lib/types";

type RunStopButtonProps = {
  run: RunState;
  busy?: boolean;
  onStop: () => void;
  onForceStop?: () => void;
  className?: string;
};

export function RunStopButton({ run, busy = false, onStop, onForceStop, className }: RunStopButtonProps) {
  const active = run.status === "running" || run.status === "stopping";
  const forcing = run.status === "stopping";
  return (
    <Button className={className} variant={forcing ? "destructive" : "outline"} onClick={forcing && onForceStop ? onForceStop : onStop} disabled={busy || !active || !run.id}>
      <Square className="size-4" />
      {forcing ? "强制停止" : "停止"}
    </Button>
  );
}
