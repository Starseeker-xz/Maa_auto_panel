import { Cog, Play, Plus, Square } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ConfigFile, RunState, TaskItem } from "@/lib/types";

type TaskListPaneProps = {
  taskConfigs: ConfigFile[];
  selectedTaskConfig: string;
  taskItems: TaskItem[];
  selectedTaskItemId: string;
  run: RunState;
  onTaskConfigChange: (name: string) => void;
  onStartRun: () => void;
  onStopRun: () => void;
};

export function TaskListPane({
  taskConfigs,
  selectedTaskConfig,
  taskItems,
  selectedTaskItemId,
  run,
  onTaskConfigChange,
  onStartRun,
  onStopRun
}: TaskListPaneProps) {
  const active = run.status === "running" || run.status === "stopping";

  return (
    <Card className="grid min-h-0 grid-rows-[auto_minmax(220px,1fr)_auto_auto] gap-3 p-3">
      <div className="grid gap-1.5">
        <label className="text-xs font-medium text-muted-foreground">当前任务配置</label>
        <Select value={selectedTaskConfig} onValueChange={onTaskConfigChange}>
          <SelectTrigger>
            <SelectValue placeholder="选择任务配置" />
          </SelectTrigger>
          <SelectContent>
            {taskConfigs.map((item) => (
              <SelectItem key={item.path} value={item.name}>
                {item.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <ScrollArea className="min-h-0">
        <div className="grid gap-1.5 pr-2">
          {taskItems.map((item) => (
            <div
              key={item.id}
              data-active={selectedTaskItemId === item.id ? "true" : undefined}
              className="grid h-10 grid-cols-[22px_minmax(0,1fr)_30px] items-center gap-2 rounded-md border bg-card px-2 shadow-xs transition-all hover:-translate-y-px hover:border-border/80 hover:shadow-md data-[active=true]:border-cyan-500 data-[active=true]:bg-cyan-50/60"
            >
              <Checkbox defaultChecked aria-label={`${item.name} 启用`} />
              <span className="truncate text-sm">{item.name}</span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button asChild variant="ghost" size="icon" aria-label={`${item.name} 设置`}>
                    <Link to={`/tasks/${encodeURIComponent(selectedTaskConfig)}/items/${encodeURIComponent(item.id)}`}>
                      <Cog className="size-4" />
                    </Link>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>任务设置</TooltipContent>
              </Tooltip>
            </div>
          ))}
        </div>
      </ScrollArea>

      <div className="grid grid-cols-[34px_1fr_1fr] gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="outline" size="icon" aria-label="新增任务配置">
              <Plus className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>新增任务配置</TooltipContent>
        </Tooltip>
        <Button variant="outline">全选</Button>
        <Button variant="outline">清空</Button>
      </div>

      <div className="grid gap-2">
        <Button className="h-11 bg-cyan-500 text-slate-950 hover:bg-cyan-400" onClick={onStartRun} disabled={active || !selectedTaskConfig}>
          <Play className="size-4" />
          Link Start!
        </Button>
        <Button variant="outline" onClick={onStopRun} disabled={!active || !run.id}>
          <Square className="size-4" />
          停止
        </Button>
      </div>
    </Card>
  );
}
