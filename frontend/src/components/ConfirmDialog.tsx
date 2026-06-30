import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  tone?: "default" | "destructive";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  tone = "default",
  busy = false,
  onConfirm,
  onCancel
}: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/30 p-4 backdrop-blur-[1px]" role="presentation">
      <Card className="w-full max-w-md gap-4 p-4 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md bg-amber-50 text-amber-700">
            <AlertTriangle className="size-4" />
          </div>
          <div className="grid gap-1">
            <h2 id="confirm-dialog-title" className="text-base font-semibold">
              {title}
            </h2>
            <p className="text-sm leading-6 text-muted-foreground">{description}</p>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            取消
          </Button>
          <Button variant={tone === "destructive" ? "destructive" : "default"} onClick={onConfirm} disabled={busy}>
            {busy ? "处理中..." : confirmLabel}
          </Button>
        </div>
      </Card>
    </div>
  );
}
