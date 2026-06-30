import { BarChart3, CalendarClock, ExternalLink, PencilLine, Play, Plus, Settings2, Square, Trash2 } from "lucide-react";
import React from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DirtyActions } from "@/components/DirtyActions";
import { ProfileEditor } from "@/components/ProfileEditor";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  createSchedule,
  deleteSchedule,
  getCurrentScheduleRun,
  listConfigs,
  listSchedules,
  readSchedule,
  readTaskConfig,
  saveSchedule,
  startScheduleRun,
  stopCurrentScheduleRun
} from "@/lib/api";
import { STATUS_LABELS } from "@/lib/logs";
import type { ConfigFile, RunState, ScheduleConfig, ScheduleEntry, ScheduleResponse, SchedulesResponse, TaskItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { LogPane } from "@/pages/main/LogPane";

type CenterTab = "settings" | "stats";

export function SchedulePage() {
  const { scheduleId } = useParams();
  const navigate = useNavigate();
  const [overview, setOverview] = React.useState<SchedulesResponse | null>(null);
  const [detail, setDetail] = React.useState<ScheduleResponse | null>(null);
  const [configs, setConfigs] = React.useState<ConfigFile[]>([]);
  const [draft, setDraft] = React.useState<ScheduleConfig | null>(null);
  const [selectedEntryId, setSelectedEntryId] = React.useState("");
  const [run, setRun] = React.useState<RunState>({ status: "idle", output: [] });
  const [newName, setNewName] = React.useState("日常定时");
  const [centerTab, setCenterTab] = React.useState<CenterTab>("settings");
  const [pendingTaskConfig, setPendingTaskConfig] = React.useState("");
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let cancelled = false;
    Promise.all([listSchedules(), listConfigs()])
      .then(([scheduleData, configData]) => {
        if (cancelled) return;
        setOverview(scheduleData);
        setConfigs(configData.tasks);
      })
      .catch((exc) => {
        if (!cancelled) setError(String(exc));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    if (!scheduleId) {
      setDetail(null);
      setDraft(null);
      return;
    }
    readSchedule(scheduleId)
      .then((data) => {
        if (cancelled) return;
        setDetail(data);
        setDraft(cloneConfig(data.config));
        setSelectedEntryId(data.config.entries[0]?.id || "");
        setError("");
      })
      .catch((exc) => {
        if (!cancelled) setError(String(exc));
      });
    return () => {
      cancelled = true;
    };
  }, [scheduleId]);

  React.useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        setRun(await getCurrentScheduleRun());
      } catch (exc) {
        setError(String(exc));
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const dirty = Boolean(detail && draft && JSON.stringify(detail.config) !== JSON.stringify(draft));

  async function refreshOverview() {
    const data = await listSchedules();
    setOverview(data);
    return data;
  }

  async function refreshDetail(id = scheduleId) {
    if (!id) return;
    const data = await readSchedule(id);
    setDetail(data);
    setDraft(cloneConfig(data.config));
    setSelectedEntryId((current) => current || data.config.entries[0]?.id || "");
  }

  async function handleCreate() {
    setBusy(true);
    setError("");
    try {
      const created = await createSchedule({ name: newName || "日常定时" });
      await refreshOverview();
      navigate(`/schedule/${encodeURIComponent(created.config.id)}`);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  async function handleSave() {
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      const saved = await saveSchedule(draft.id, draft as unknown as Record<string, unknown>);
      setDetail(saved);
      setDraft(cloneConfig(saved.config));
      await refreshOverview();
    } catch (exc) {
      setError(String(exc));
      throw exc;
    } finally {
      setBusy(false);
    }
  }

  async function handleReset() {
    if (!detail) return;
    setDraft(cloneConfig(detail.config));
    setSelectedEntryId(detail.config.entries[0]?.id || "");
  }

  async function handleDelete() {
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      await deleteSchedule(draft.id);
      const data = await refreshOverview();
      const next = data.schedules[0]?.id || "";
      navigate(next ? `/schedule/${encodeURIComponent(next)}` : "/schedule", { replace: true });
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
      setDeleteOpen(false);
    }
  }

  async function handleTaskConfigConfirm() {
    if (!draft || !pendingTaskConfig) return;
    const taskConfig = await readTaskConfig(pendingTaskConfig);
    const taskIds = (taskConfig.task_items || []).map((item) => item.id);
    setDraft({
      ...draft,
      task_config: pendingTaskConfig,
      entries: draft.entries.map((entry) => ({ ...entry, task_ids: taskIds }))
    });
    setPendingTaskConfig("");
  }

  async function handleStart() {
    if (!draft) return;
    setError("");
    try {
      setRun(await startScheduleRun(draft.id, selectedEntryId || draft.entries[0]?.id));
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function handleStop() {
    try {
      setRun(await stopCurrentScheduleRun());
    } catch (exc) {
      setError(String(exc));
    }
  }

  if (!scheduleId) {
    return (
      <section className="min-h-screen overflow-auto p-4">
        <div className="grid gap-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h1 className="text-lg font-semibold">定时执行</h1>
              <div className="text-xs text-muted-foreground">
                {overview?.status.enabled ? "调度器已启用" : "调度器未启用"} · 最近 {overview?.status.recent_runs.length || 0} 条运行记录
              </div>
            </div>
            <div className="grid grid-cols-[minmax(0,12rem)_auto] gap-2">
              <Input value={newName} onChange={(event) => setNewName(event.target.value)} />
              <Button onClick={handleCreate} disabled={busy}>
                <Plus className="size-4" />
                新建
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-3">
            {(overview?.schedules || []).map((item) => (
              <Card key={item.id} className="cursor-pointer gap-3 p-3 transition-colors hover:border-primary/60" onClick={() => navigate(`/schedule/${encodeURIComponent(item.id)}`)}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="truncate text-sm">{item.name}</CardTitle>
                    <div className="mt-1 break-anywhere text-xs text-muted-foreground">{item.path}</div>
                  </div>
                  <CalendarClock className="size-4 shrink-0 text-muted-foreground" />
                </div>
                {item.last_run ? (
                  <div className="grid gap-1 text-xs">
                    <span className={`status-pill ${item.last_run.status}`}>{STATUS_LABELS[item.last_run.status] || item.last_run.status}</span>
                    <span className="text-muted-foreground">{item.last_run.entry_name} · {item.last_run.created_at}</span>
                  </div>
                ) : (
                  <span className="status-pill idle">暂无运行记录</span>
                )}
              </Card>
            ))}
            {overview && overview.schedules.length === 0 ? (
              <Card className="grid min-h-40 place-items-center border-dashed p-4 text-sm text-muted-foreground">暂无定时配置</Card>
            ) : null}
          </div>
          {error ? <div className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">{error}</div> : null}
        </div>
      </section>
    );
  }

  if (!draft || !detail) {
    return (
      <section className="min-h-screen p-4">
        <Card className="min-h-[calc(100vh-2rem)] gap-3 p-4">
          <CardTitle>定时执行</CardTitle>
          <div className="text-sm text-muted-foreground">{error || "正在读取定时配置..."}</div>
        </Card>
      </section>
    );
  }

  const selectedEntry = draft.entries.find((entry) => entry.id === selectedEntryId) || draft.entries[0];
  const taskItems = detail.task_config.task_items || [];
  const active = run.status === "running" || run.status === "stopping";
  const sortedEntries = sortEntriesByReset(draft.entries, detail.timeline.reset_local_time);

  return (
    <section className="grid h-screen min-h-0 grid-cols-[310px_minmax(460px,1fr)_360px] gap-4 overflow-hidden p-4 max-xl:grid-cols-[300px_minmax(360px,1fr)] max-md:h-auto max-md:grid-cols-1 max-md:overflow-auto max-md:p-2">
      <ScheduleLeftPane
        configs={configs}
        schedule={draft}
        taskItems={taskItems}
        entries={sortedEntries}
        selectedEntry={selectedEntry}
        onScheduleChange={setDraft}
        onEntrySelect={setSelectedEntryId}
        onTaskConfigChange={setPendingTaskConfig}
        onOpenTaskConfig={() => navigate(`/tasks/${encodeURIComponent(draft.task_config)}`)}
      />

      <Card className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-3 overflow-hidden p-3">
        <div className="flex items-center justify-between gap-3">
          <div className="inline-grid grid-cols-2 rounded-md border bg-muted p-0.5">
            <button type="button" className={tabClass(centerTab === "settings")} onClick={() => setCenterTab("settings")}>
              <Settings2 className="size-4" />
              设置
            </button>
            <button type="button" className={tabClass(centerTab === "stats")} onClick={() => setCenterTab("stats")}>
              <BarChart3 className="size-4" />
              统计
            </button>
          </div>
          <span className="min-w-0 truncate text-xs text-muted-foreground">{detail.timeline.message}</span>
        </div>
        <ScrollArea className="min-h-0">
          {centerTab === "settings" ? (
            <ScheduleSettings
              schedule={draft}
              detail={detail}
              onChange={setDraft}
            />
          ) : (
            <ScheduleStats detail={detail} />
          )}
        </ScrollArea>
        <div className="grid grid-cols-[1fr_1fr_auto] gap-2">
          <Button onClick={handleStart} disabled={active || !selectedEntry}>
            <Play className="size-4" />
            运行当前时间点
          </Button>
          <Button variant="outline" onClick={handleStop} disabled={!active}>
            <Square className="size-4" />
            停止
          </Button>
          <Button variant="outline" size="icon" aria-label="删除定时配置" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="size-4" />
          </Button>
        </div>
      </Card>

      <LogPane run={run} error={error} title="定时执行日志" emptyText="等待定时执行日志..." />

      <DirtyActions
        dirty={dirty}
        busy={busy}
        saveTitle="保存定时配置"
        saveDescription={`将当前定时配置写入 ${detail.file.filename}。`}
        resetTitle="复位定时配置"
        resetDescription="复位会丢弃当前未保存修改，并重新载入磁盘上的定时配置。"
        onSave={handleSave}
        onReset={handleReset}
      />
      <ConfirmDialog
        open={Boolean(pendingTaskConfig)}
        title="更换绑定任务配置"
        description="更换后，每个时间点的子任务启用列表会按新的任务配置重置。"
        confirmLabel="更换"
        busy={busy}
        onCancel={() => setPendingTaskConfig("")}
        onConfirm={() => void handleTaskConfigConfirm()}
      />
      <ConfirmDialog
        open={deleteOpen}
        title="删除定时配置"
        description={`删除 ${draft.name} 后，配置文件会移动到回收站。`}
        confirmLabel="删除"
        tone="destructive"
        busy={busy}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={() => void handleDelete()}
      />
    </section>
  );
}

function ScheduleLeftPane({
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
    const nextIds = enabled
      ? Array.from(new Set([...selectedEntry.task_ids, taskId]))
      : selectedEntry.task_ids.filter((item) => item !== taskId);
    updateEntry(selectedEntry.id, { task_ids: nextIds });
  }

  function addEntry() {
    const id = `t${Math.random().toString(16).slice(2, 8)}`;
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
                    <Button
                      data-entry-control
                      variant="ghost"
                      size="icon"
                      className="size-6 text-muted-foreground/70 opacity-0 transition-opacity hover:text-destructive hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-70"
                      aria-label={`${entry.name} 删除`}
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        if (renamingEntryId === entry.id) cancelEntryRename();
                        deleteEntry(entry.id);
                      }}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
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
        <CardTitle className="text-sm">{selectedEntry?.name || "子任务启用"}</CardTitle>
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

function ScheduleSettings({ schedule, detail, onChange }: { schedule: ScheduleConfig; detail: ScheduleResponse; onChange: (schedule: ScheduleConfig) => void }) {
  const selectedScript = detail.scripts.find((script) => script.name === schedule.restart.script);

  return (
    <div className="grid gap-3 pr-3">
      <section className="grid gap-3 rounded-md border bg-background p-3">
        <CardTitle className="text-sm">设备配置</CardTitle>
        <ProfileEditor value={schedule.profile} onChange={(profile) => onChange({ ...schedule, profile })} />
      </section>

      <section className="grid gap-3 rounded-md border bg-background p-3">
        <CardTitle className="text-sm">超时与重试</CardTitle>
        <div className="grid grid-cols-3 gap-2 max-lg:grid-cols-2 max-sm:grid-cols-1">
          <NumberInput label="子任务警报" value={schedule.timeouts.child_warning_seconds} onChange={(value) => updateTimeout(schedule, onChange, "child_warning_seconds", value)} />
          <NumberInput label="子任务危险警报" value={schedule.timeouts.child_danger_seconds} onChange={(value) => updateTimeout(schedule, onChange, "child_danger_seconds", value)} />
          <NumberInput label="子任务硬停止" value={schedule.timeouts.child_kill_seconds} onChange={(value) => updateTimeout(schedule, onChange, "child_kill_seconds", value)} />
          <NumberInput label="整组警报" value={schedule.timeouts.run_warning_seconds} onChange={(value) => updateTimeout(schedule, onChange, "run_warning_seconds", value)} />
          <NumberInput label="整组危险警报" value={schedule.timeouts.run_danger_seconds} onChange={(value) => updateTimeout(schedule, onChange, "run_danger_seconds", value)} />
          <NumberInput label="整组硬停止" value={schedule.timeouts.run_kill_seconds} onChange={(value) => updateTimeout(schedule, onChange, "run_kill_seconds", value)} />
          <NumberInput label="单组重试上限" value={schedule.retry.max_attempts_per_group} onChange={(value) => onChange({ ...schedule, retry: { ...schedule.retry, max_attempts_per_group: value } })} />
          <NumberInput label="重试组缓冲" value={schedule.retry.group_buffer_seconds} onChange={(value) => onChange({ ...schedule, retry: { ...schedule.retry, group_buffer_seconds: value } })} />
          <NumberInput label="重试组上限" value={schedule.retry.max_groups} onChange={(value) => onChange({ ...schedule, retry: { ...schedule.retry, max_groups: value } })} />
        </div>
      </section>

      <section className="grid gap-3 rounded-md border bg-background p-3">
        <CardTitle className="text-sm">脚本</CardTitle>
        <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
          <Select value={schedule.restart.mode} onValueChange={(mode) => onChange({ ...schedule, restart: { ...schedule.restart, mode: mode as ScheduleConfig["restart"]["mode"] } })}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">不重启</SelectItem>
              <SelectItem value="before_run">运行前重启</SelectItem>
              <SelectItem value="before_retry_group">重试组前重启</SelectItem>
              <SelectItem value="before_retry">每次重试前重启</SelectItem>
            </SelectContent>
          </Select>
          <Select value={schedule.restart.script || "__none"} onValueChange={(script) => onChange({ ...schedule, restart: { ...schedule.restart, script: script === "__none" ? "" : script } })}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none">未选择脚本</SelectItem>
              {detail.scripts.map((script) => (
                <SelectItem key={script.name} value={script.name}>
                  {script.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {selectedScript?.variables.length ? (
          <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
            {selectedScript.variables.map((variable) => (
              <label key={variable.name} className="grid gap-1.5">
                <span className="text-xs font-medium text-muted-foreground">{variable.label}</span>
                <Input
                  value={schedule.restart.variables[variable.name] ?? variable.default}
                  onChange={(event) =>
                    onChange({
                      ...schedule,
                      restart: {
                        ...schedule.restart,
                        variables: { ...schedule.restart.variables, [variable.name]: event.target.value }
                      }
                    })
                  }
                />
              </label>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}

function ScheduleStats({ detail }: { detail: ScheduleResponse }) {
  return (
    <div className="grid gap-3 pr-3">
      <section className="grid gap-2 rounded-md border bg-background p-3">
        <CardTitle className="text-sm">今日计数</CardTitle>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2">
          {detail.task_policies.map((policy) => {
            const stats = detail.daily_stats[policy.id];
            return (
              <div key={policy.id} className="rounded-md border bg-card p-2 text-xs">
                <div className="truncate font-medium">{policy.name}</div>
                <div className="mt-1 text-muted-foreground">成功 {stats?.successes || 0} · 运行 {stats?.runs || 0}</div>
              </div>
            );
          })}
        </div>
      </section>
      <section className="grid gap-2 rounded-md border bg-background p-3">
        <CardTitle className="text-sm">近期运行</CardTitle>
        <div className="grid gap-2">
          {detail.recent_runs.map((item) => (
            <div key={item.id} className="grid gap-1 rounded-md border bg-card p-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className={`status-pill ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span>
                <span className="text-muted-foreground">{item.created_at}</span>
              </div>
              <div className="text-muted-foreground">{item.entry_name} · 尝试 {item.attempt_count} · 重试组 {item.retry_group_count}</div>
            </div>
          ))}
          {detail.recent_runs.length === 0 ? <CardContent className="p-0 text-xs text-muted-foreground">暂无运行记录</CardContent> : null}
        </div>
      </section>
    </div>
  );
}

function NumberInput({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="grid min-w-0 gap-1.5">
      <span className="truncate text-xs font-medium text-muted-foreground">{label}</span>
      <Input className="min-w-0" type="number" min={0} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function updateTimeout(schedule: ScheduleConfig, onChange: (schedule: ScheduleConfig) => void, key: keyof ScheduleConfig["timeouts"], value: number) {
  onChange({ ...schedule, timeouts: { ...schedule.timeouts, [key]: value } });
}

function cloneConfig(config: ScheduleConfig): ScheduleConfig {
  return JSON.parse(JSON.stringify(config)) as ScheduleConfig;
}

function sortEntriesByReset(entries: ScheduleEntry[], resetTime: string) {
  const reset = minutes(resetTime);
  return [...entries].sort((left, right) => ((minutes(left.time) - reset + 1440) % 1440) - ((minutes(right.time) - reset + 1440) % 1440));
}

function minutes(value: string) {
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(Math.round(value), min), max);
}

function tabClass(active: boolean) {
  return cn("inline-flex h-8 items-center justify-center gap-1.5 rounded-sm px-3 text-sm", active ? "bg-background shadow-xs" : "text-muted-foreground");
}
