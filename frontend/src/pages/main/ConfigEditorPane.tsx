import { Card, CardTitle } from "@/components/ui/card";
import type { TaskItem } from "@/lib/types";

type ConfigEditorPaneProps = {
  taskConfig: string;
  selectedTaskItem?: TaskItem;
};

export function ConfigEditorPane({ taskConfig, selectedTaskItem }: ConfigEditorPaneProps) {
  return (
    <Card className="grid min-h-0 grid-rows-[auto_minmax(240px,1fr)] gap-3 p-4">
      <CardTitle>配置编辑</CardTitle>
      <div className="grid place-items-center rounded-xl border border-dashed bg-muted/20">
        <div className="grid gap-1 text-center">
          <div className="font-semibold">{selectedTaskItem?.name || taskConfig || "未选择任务配置"}</div>
          <div className="text-sm text-muted-foreground">
            {selectedTaskItem ? "后续在这里编辑该子任务配置" : "后续在这里做可视化配置编辑"}
          </div>
        </div>
      </div>
    </Card>
  );
}
