import { ExternalLink, PencilLine, Plus } from "lucide-react";
import React from "react";

import { Button } from "@/components/ui/button";
import { FocusDeleteButton } from "@/components/FocusDeleteButton";
import { Card, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { ConfigFile, ScheduleConfig, ScheduleEntry, TaskItem } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ScheduleLeftPane({
  configs,
  schedule,
  taskItems,
  entries,
  selectedEntry,
  onScheduleChange,
  onEntrySelect,
  onTaskConfigChange,
  onOpenTaskConfig
}: {
  configs: ConfigFile[];
  schedule: ScheduleConfig;
  taskItems: TaskItem[];
  entries: ScheduleEntry[];
  selectedEntry?: ScheduleEntry;
  onScheduleChange: (schedule: ScheduleConfig) => void;
  onEntrySelect: (entryId: string) => void;
  onTaskConfigChange: (taskConfig: string) => void;
  onOpenTaskConfig: () => void;
}) {
  const [renamingEntryId, setRenamingEntryId] = React.useState("");
  const [renameDraft, setRenameDraft] = React.useState("");
  const [entryPaneHeight, setEntryPaneHeight] = React.useState<number | null>(null);
  const skipRenameBlurCommit = React.useRef(false);
  const cardRef = React.useRef<HTMLDivElement>(null);
  const entryPaneRef = React.useRef<HTMLElement>(null);

  function updateEntry(entryId: string, patch: Partial<ScheduleEntry>) {
    onScheduleChange({
      ...schedule,
      entries: schedule.entries.map((entry) => (entry.id === entryId ? { ...entry, ...patch } : entry))
    });
  }

  function startEntryRename(entry: ScheduleEntry) {
    skipRenameBlurCommit.current = false;
    setRenamingEntryId(entry.id);
    setRenameDraft(entry.name);
  }

  function commitEntryRename() {
    if (skipRenameBlurCommit.current) {
      skipRenameBlurCommit.current = false;
      return;
    }
    if (!renamingEntryId) return;
    updateEntry(renamingEntryId, { name: renameDraft.trim() || "未命名时间点" });
    setRenamingEntryId("");
    setRenameDraft("");
  }

  function cancelEntryRename() {
    skipRenameBlurCommit.current = true;
    setRenamingEntryId("");
    setRenameDraft("");
  }

  function toggleTask(taskId: string, enabled: boolean) {
    if (!selectedEntry) return;
    const nextIds = enabled ? Array.from(new Set([...selectedEntry.task_ids, taskId])) : selectedEntry.task_ids.filter((item) => item !== taskId);
    updateEntry(selectedEntry.id, { task_ids: nextIds });
  }

  function addEntry() {
    const id = createEntryId(schedule.entries);
    const entry = {
      id,
      name: "新时间点",
      time: "04:00",
      enabled: true,
      task_ids: taskItems.map((item) => item.id)
    };
    onScheduleChange({ ...schedule, entries: [...schedule.entries, entry] });
    onEntrySelect(id);
  }

  function deleteEntry(entryId: string) {
    const nextEntries = schedule.entries.filter((entry) => entry.id !== entryId);
    onScheduleChange({ ...schedule, entries: nextEntries });
    if (selectedEntry?.id === entryId) onEntrySelect(nextEntries[0]?.id || "");
  }

  function entryControlTarget(target: EventTarget | null) {
    return target instanceof HTMLElement && Boolean(target.closest("[data-entry-control]"));
  }

  function entryPaneHeightBounds() {
    const cardHeight = cardRef.current?.getBoundingClientRect().height || 620;
    return {
      min: 112,
      max: Math.max(150, cardHeight - 310)
    };
  }

  function startEntryPaneResize(event: React.PointerEvent<HTMLDivElement>) {
    const pane = entryPaneRef.current;
    if (!pane) return;
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = pane.getBoundingClientRect().height;
    const previousCursor = document.body.style.cursor;
    const previousSelect = document.body.style.userSelect;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";

    const handleMove = (moveEvent: PointerEvent) => {
      const bounds = entryPaneHeightBounds();
      setEntryPaneHeight(clamp(startHeight + moveEvent.clientY - startY, bounds.min, bounds.max));
    };
    const handleUp = () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousSelect;
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp, { once: true });
  }

  function resizeEntryPaneWithKeyboard(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const current = entryPaneHeight ?? entryPaneRef.current?.getBoundingClientRect().height ?? 220;
    const bounds = entryPaneHeightBounds();
    setEntryPaneHeight(clamp(current + (event.key === "ArrowDown" ? 24 : -24), bounds.min, bounds.max));
  }

  return (
    <Card
      ref={cardRef}
      className={cn(
        "grid h-full min-h-0 gap-2 overflow-hidden p-3",
        entryPaneHeight === null ? "grid-rows-[auto_minmax(180px,1.6fr)_8px_minmax(150px,1fr)]" : ""
      )}
      style={entryPaneHeight !== null ? { gridTemplateRows: `auto ${entryPaneHeight}px 8px minmax(150px, 1fr)` } : undefined}
    >
      <div className="grid gap-2">
        <Input value={schedule.name} onChange={(event) => onScheduleChange({ ...schedule, name: event.target.value })} />
        <div className="grid grid-cols-[minmax(0,1fr)_34px] gap-1.5">
          <Select value={schedule.task_config} onValueChange={onTaskConfigChange}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {configs.map((item) => (
                <SelectItem key={item.path} value={item.name}>
                  {item.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" aria-label="打开任务配置" onClick={onOpenTaskConfig}>
            <ExternalLink className="size-4" />
          </Button>
        </div>
        <label className="flex min-h-9 items-center gap-2 rounded-md border px-2.5 py-2">
          <Checkbox checked={schedule.enabled} onCheckedChange={(value) => onScheduleChange({ ...schedule, enabled: value === true })} />
          <span className="text-sm">启用该定时配置</span>
        </label>
      </div>

      <section ref={entryPaneRef} className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm">时间表</CardTitle>
          <Button variant="outline" size="sm" onClick={addEntry}>
            <Plus className="size-3.5" />
            新增
          </Button>
        </div>
        <ScrollArea className="min-h-0">
          <div className="grid gap-1.5 pr-2">
            {entries.map((entry) => (
              <div
                key={entry.id}
                data-active={entry.id === selectedEntry?.id ? "true" : undefined}
                className="group grid min-h-[3.55rem] cursor-pointer gap-1 rounded-md border bg-card p-1.5 shadow-xs transition-all hover:-translate-y-px hover:border-border/80 hover:shadow-md data-[active=true]:border-primary data-[active=true]:bg-accent/70"
                role="button"
                tabIndex={0}
                onClick={(event) => {
                  if (!entryControlTarget(event.target)) onEntrySelect(entry.id);
                }}
                onKeyDown={(event) => {
                  if (entryControlTarget(event.target)) return;
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onEntrySelect(entry.id);
                  }
                }}
              >
                <div className="grid grid-cols-[20px_minmax(0,1fr)_52px] items-center gap-1">
                  <Checkbox data-entry-control checked={entry.enabled} aria-label={`${entry.name} 启用`} onCheckedChange={(value) => updateEntry(entry.id, { enabled: value === true })} />
                  {renamingEntryId === entry.id ? (
                    <Input
                      data-entry-control
                      className="h-7 min-w-0 px-2"
                      value={renameDraft}
                      onChange={(event) => setRenameDraft(event.target.value)}
                      onBlur={commitEntryRename}
                      onClick={(event) => event.stopPropagation()}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") commitEntryRename();
                        if (event.key === "Escape") cancelEntryRename();
                      }}
                      autoFocus
                    />
                  ) : (
                    <span className="min-w-0 truncate text-sm font-medium">{entry.name}</span>
                  )}
                  <div className="flex items-center justify-end gap-0.5">
                    <Button
                      data-entry-control
                      variant="ghost"
                      size="icon"
                      className="size-6 text-muted-foreground/70 opacity-0 transition-opacity hover:text-foreground hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-70"
                      aria-label={`${entry.name} 重命名`}
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        startEntryRename(entry);
                      }}
                    >
                      <PencilLine className="size-3.5" />
                    </Button>
                    <FocusDeleteButton
                      data-entry-control
                      className="size-6"
                      aria-label={`${entry.name} 删除`}
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        if (renamingEntryId === entry.id) cancelEntryRename();
                        deleteEntry(entry.id);
                      }}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-[20px_minmax(0,1fr)] items-center gap-1">
                  <span aria-hidden="true" />
                  <Input data-entry-control className="h-7 !w-[6.75rem] justify-self-start px-2 text-sm" type="time" value={entry.time} onChange={(event) => updateEntry(entry.id, { time: event.target.value })} />
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </section>

      <div
        className="group flex cursor-row-resize items-center py-1"
        role="separator"
        aria-orientation="horizontal"
        aria-label="调整时间表和子任务列表高度"
        tabIndex={0}
        onPointerDown={startEntryPaneResize}
        onKeyDown={resizeEntryPaneWithKeyboard}
      >
        <div className="h-px flex-1 bg-border transition-colors group-hover:bg-primary/60 group-focus-visible:bg-primary/70" />
      </div>

      <section className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-2">
        <CardTitle className="text-sm">{selectedEntry?.name + " · 启用子任务" || "启用子任务"}</CardTitle>
        <ScrollArea className="min-h-0">
          <div className="grid grid-cols-2 gap-1.5 pr-2">
            {taskItems.map((item) => (
              <label key={item.id} className="flex min-h-9 min-w-0 items-center gap-2 rounded-md border bg-background px-2 text-sm">
                <Checkbox checked={Boolean(selectedEntry?.task_ids.includes(item.id))} onCheckedChange={(value) => toggleTask(item.id, value === true)} />
                <span className="min-w-0 truncate">{item.name}</span>
              </label>
            ))}
          </div>
        </ScrollArea>
      </section>
    </Card>
  );
}

function createEntryId(entries: ScheduleEntry[]) {
  const used = new Set(entries.map((entry) => entry.id));
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const randomPart = globalThis.crypto?.randomUUID?.().replace(/-/g, "").slice(0, 8) || Math.random().toString(16).slice(2, 10);
    const id = `t${randomPart}`;
    if (!used.has(id)) return id;
  }
  return `t${Date.now().toString(16)}`;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(Math.round(value), min), max);
}
