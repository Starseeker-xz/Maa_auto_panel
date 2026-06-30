import { GripVertical, PencilLine, Play, Plus, Square, Trash2 } from "lucide-react";
import React from "react";
import { useNavigate } from "react-router-dom";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { taskItemDefaults } from "@/lib/taskItemDefaults";
import type { ConfigFile, RunState, TaskItem } from "@/lib/types";

type TaskListPaneProps = {
  taskConfigs: ConfigFile[];
  selectedTaskConfig: string;
  taskItems: TaskItem[];
  selectedTaskItemId: string;
  run: RunState;
  onTaskConfigChange: (name: string) => void;
  onTaskConfigCreate: (name: string) => void;
  onTaskConfigDelete: () => void;
  onTaskItemAdd: (type: string) => void;
  onTaskItemRename: (itemId: string, name: string) => void;
  onTaskItemDelete: (itemId: string) => void;
  onTaskItemEnabledChange: (itemId: string, enabled: boolean) => void;
  onAllTaskItemsEnabledChange: (enabled: boolean) => void;
  onTaskItemsReorder: (sourceId: string, targetIndex: number) => void;
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
  onTaskConfigCreate,
  onTaskConfigDelete,
  onTaskItemAdd,
  onTaskItemRename,
  onTaskItemDelete,
  onTaskItemEnabledChange,
  onAllTaskItemsEnabledChange,
  onTaskItemsReorder,
  onStartRun,
  onStopRun
}: TaskListPaneProps) {
  const navigate = useNavigate();
  const active = run.status === "running" || run.status === "stopping";
  const [draggingId, setDraggingId] = React.useState<string>("");
  const [dropIndex, setDropIndex] = React.useState<number | null>(null);
  const [creatingConfig, setCreatingConfig] = React.useState(false);
  const [newConfigName, setNewConfigName] = React.useState("");
  const [renamingId, setRenamingId] = React.useState("");
  const [renameDraft, setRenameDraft] = React.useState("");
  const skipRenameBlurCommit = React.useRef(false);

  function handleCreateConfig() {
    const name = newConfigName.trim();
    if (!name) return;
    onTaskConfigCreate(name);
    setNewConfigName("");
    setCreatingConfig(false);
  }

  function updateDropIndex(event: React.DragEvent<HTMLElement>, index: number) {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const nextIndex = event.clientY < rect.top + rect.height / 2 ? index : index + 1;
    setDropIndex(nextIndex);
    event.dataTransfer.dropEffect = "move";
  }

  function handleDrop(event: React.DragEvent<HTMLElement>) {
    event.preventDefault();
    const sourceId = event.dataTransfer.getData("text/task-item-id") || draggingId;
    const targetIndex = dropIndex;
    setDraggingId("");
    setDropIndex(null);
    if (sourceId && targetIndex !== null) onTaskItemsReorder(sourceId, targetIndex);
  }

  function startRename(item: TaskItem) {
    skipRenameBlurCommit.current = false;
    setRenamingId(item.id);
    setRenameDraft(item.name);
  }

  function commitRename() {
    if (skipRenameBlurCommit.current) {
      skipRenameBlurCommit.current = false;
      return;
    }
    if (!renamingId) return;
    onTaskItemRename(renamingId, renameDraft);
    setRenamingId("");
    setRenameDraft("");
  }

  function cancelRename() {
    skipRenameBlurCommit.current = true;
    setRenamingId("");
    setRenameDraft("");
  }

  function openTaskItem(itemId: string) {
    if (!selectedTaskConfig) return;
    navigate(`/tasks/${encodeURIComponent(selectedTaskConfig)}/items/${encodeURIComponent(itemId)}`);
  }

  function rowControlTarget(target: EventTarget | null) {
    return target instanceof HTMLElement && Boolean(target.closest("[data-row-control]"));
  }

  return (
    <Card className="grid h-full min-h-0 grid-rows-[auto_minmax(220px,1fr)_auto_auto] gap-3 overflow-hidden p-3">
      <div className="grid gap-1.5">
        <label className="text-xs font-medium text-muted-foreground">当前任务配置</label>
        <div className="grid grid-cols-[minmax(0,1fr)_34px_34px] gap-1.5">
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
          <Button variant="outline" size="icon" aria-label="新增任务配置" onClick={() => setCreatingConfig((value) => !value)}>
            <Plus className="size-4" />
          </Button>
          <Button variant="outline" size="icon" aria-label="删除当前任务配置" onClick={onTaskConfigDelete} disabled={!selectedTaskConfig}>
            <Trash2 className="size-4" />
          </Button>
        </div>
        {creatingConfig ? (
          <div className="grid animate-in grid-cols-[minmax(0,1fr)_58px] gap-1.5 fade-in slide-in-from-top-1 duration-150">
            <Input
              value={newConfigName}
              placeholder="名称"
              onChange={(event) => setNewConfigName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") handleCreateConfig();
                if (event.key === "Escape") setCreatingConfig(false);
              }}
              autoFocus
            />
            <Button variant="outline" onClick={handleCreateConfig} disabled={!newConfigName.trim()}>
              确定
            </Button>
          </div>
        ) : null}
      </div>

      <ScrollArea className="min-h-0">
        <div
          className="grid gap-1.5 pt-1"
          onDragLeave={(event) => {
            const nextTarget = event.relatedTarget as Node | null;
            if (nextTarget && event.currentTarget.contains(nextTarget)) return;
            setDropIndex(null);
          }}
        >
          {taskItems.map((item, index) => (
            <div key={item.id} className="relative" onDragOver={(event) => updateDropIndex(event, index)} onDrop={handleDrop}>
              <InsertionLine active={Boolean(draggingId) && dropIndex === index && draggingId !== item.id} position={index === 0 ? "first" : "top"} />
              <div
                data-task-row
                data-active={selectedTaskItemId === item.id ? "true" : undefined}
                data-dragging={draggingId === item.id ? "true" : undefined}
                className="group grid h-10 cursor-pointer grid-cols-[22px_minmax(0,1fr)_74px] items-center gap-1.5 rounded-md border bg-card px-2 shadow-xs transition-all hover:-translate-y-px hover:border-border/80 hover:shadow-md data-[active=true]:border-primary data-[active=true]:bg-accent/70 data-[dragging=true]:scale-[0.98] data-[dragging=true]:opacity-45"
                role="link"
                tabIndex={0}
                onClick={(event) => {
                  if (!rowControlTarget(event.target)) openTaskItem(item.id);
                }}
                onKeyDown={(event) => {
                  if (rowControlTarget(event.target)) return;
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openTaskItem(item.id);
                  }
                }}
              >
                <Checkbox
                  data-row-control
                  checked={item.enabled}
                  aria-label={`${item.name} 启用`}
                  onCheckedChange={(checked) => onTaskItemEnabledChange(item.id, checked === true)}
                />
                {renamingId === item.id ? (
                  <Input
                    data-row-control
                    className="h-7 min-w-0 px-2"
                    value={renameDraft}
                    onChange={(event) => setRenameDraft(event.target.value)}
                    onBlur={commitRename}
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") commitRename();
                      if (event.key === "Escape") cancelRename();
                    }}
                    autoFocus
                  />
                ) : (
                  <div className="grid min-w-0 gap-0.5" aria-label={`编辑 ${item.name}`}>
                    <span className="truncate text-sm">{item.name}</span>
                  </div>
                )}
                <div className="flex items-center justify-end gap-0.5">
                  <Button
                    data-row-control
                    variant="ghost"
                    size="icon"
                    className="size-7 text-muted-foreground/70 opacity-0 transition-opacity hover:text-foreground hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-70"
                    aria-label={`${item.name} 重命名`}
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      startRename(item);
                    }}
                  >
                    <PencilLine className="size-3.5" />
                  </Button>
                  <Button
                    data-row-control
                    variant="ghost"
                    size="icon"
                    className="size-7 text-muted-foreground/70 opacity-0 transition-opacity hover:text-destructive hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-70"
                    aria-label={`${item.name} 删除`}
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      if (renamingId === item.id) cancelRename();
                      onTaskItemDelete(item.id);
                    }}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                  <div
                    data-drag-handle
                    data-row-control
                    className={buttonVariants({ variant: "ghost", size: "icon", className: "size-7 cursor-grab active:cursor-grabbing" })}
                    role="button"
                    tabIndex={0}
                    aria-label={`${item.name} 拖动排序`}
                    draggable
                    onDragStart={(event) => {
                      setDraggingId(item.id);
                      setDropIndex(index);
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/task-item-id", item.id);
                      const row = event.currentTarget.closest("[data-task-row]");
                      if (row instanceof HTMLElement) event.dataTransfer.setDragImage(row, 16, 20);
                    }}
                    onDragEnd={() => {
                      setDraggingId("");
                      setDropIndex(null);
                    }}
                  >
                    <GripVertical className="size-4 text-muted-foreground" />
                  </div>
                </div>
              </div>
              <InsertionLine active={Boolean(draggingId) && dropIndex === taskItems.length && index === taskItems.length - 1} position="bottom" />
            </div>
          ))}
        </div>
      </ScrollArea>

      <div className="grid grid-cols-[34px_1fr_1fr] gap-1">
        <Select value="" onValueChange={onTaskItemAdd} disabled={!selectedTaskConfig}>
          <SelectTrigger hideIcon className="h-9 w-[34px] justify-center px-0" aria-label="新增子任务">
            <SelectValue
              placeholder={
                <span className="grid place-items-center">
                  <Plus className="size-4" />
                </span>
              }
            />
          </SelectTrigger>
          <SelectContent side="top" align="start">
            {taskItemDefaults.map((item) => (
              <SelectItem key={item.type} value={item.type}>
                {item.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" onClick={() => onAllTaskItemsEnabledChange(true)}>
          全选
        </Button>
        <Button variant="outline" onClick={() => onAllTaskItemsEnabledChange(false)}>
          清空
        </Button>
      </div>

      <div className="grid gap-2">
        <Button className="h-11" onClick={onStartRun} disabled={active || !selectedTaskConfig}>
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

function InsertionLine({ active, position }: { active: boolean; position: "first" | "top" | "bottom" }) {
  if (!active) return null;
  const positionClass = position === "first" ? "top-0" : position === "top" ? "-top-1" : "-bottom-1";
  return (
    <div
      className={`pointer-events-none absolute left-1 right-1 z-10 h-0.5 rounded-full bg-primary ${positionClass}`}
    />
  );
}
