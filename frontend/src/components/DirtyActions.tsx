import React from "react";
import { RotateCcw, Save } from "lucide-react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";

type DirtyAction = "save" | "reset" | null;

type DirtyActionsProps = {
  dirty: boolean;
  busy?: boolean;
  saveTitle: string;
  saveDescription: string;
  resetTitle: string;
  resetDescription: string;
  onSave: () => void | Promise<void>;
  onReset: () => void | Promise<void>;
};

export function DirtyActions({
  dirty,
  busy = false,
  saveTitle,
  saveDescription,
  resetTitle,
  resetDescription,
  onSave,
  onReset
}: DirtyActionsProps) {
  const [action, setAction] = React.useState<DirtyAction>(null);

  React.useEffect(() => {
    if (!dirty) setAction(null);
  }, [dirty]);

  if (!dirty) return null;

  const dialog =
    action === "save"
      ? {
          title: saveTitle,
          description: saveDescription,
          confirmLabel: "保存",
          tone: "default" as const,
          run: onSave
        }
      : action === "reset"
        ? {
            title: resetTitle,
            description: resetDescription,
            confirmLabel: "复位",
            tone: "destructive" as const,
            run: onReset
          }
        : null;

  return (
    <>
      <div className="fixed right-6 bottom-6 z-30 flex gap-2 rounded-md border bg-card p-2 shadow-lg max-md:right-3 max-md:bottom-3">
        <Button onClick={() => setAction("save")}>
          <Save className="size-4" />
          保存
        </Button>
        <Button variant="outline" onClick={() => setAction("reset")}>
          <RotateCcw className="size-4" />
          复位
        </Button>
      </div>
      <ConfirmDialog
        open={Boolean(dialog)}
        title={dialog?.title || ""}
        description={dialog?.description || ""}
        confirmLabel={dialog?.confirmLabel || ""}
        tone={dialog?.tone}
        busy={busy}
        onCancel={() => setAction(null)}
        onConfirm={() => {
          if (!dialog) return;
          void Promise.resolve(dialog.run())
            .then(() => setAction(null))
            .catch(() => undefined);
        }}
      />
    </>
  );
}
