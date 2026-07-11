import { BarChart3, CalendarClock, Play, Plus, Settings2, Trash2 } from "lucide-react";
import React from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DirtyActions } from "@/components/DirtyActions";
import { SegmentedControl } from "@/components/SegmentedControl";
import { RunStopButton } from "@/components/RunStopButton";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  createSchedule,
  currentScheduleRunEventsUrl,
  deleteRunHistory,
  deleteSchedule,
  forceStopCurrentScheduleRun,
  getCurrentScheduleRun,
  getRunHistory,
  listConfigs,
  listSchedules,
  readSchedule,
  readTaskConfig,
  saveSchedule,
  startScheduleRun,
  stopCurrentScheduleRun
} from "@/lib/api";
import { STATUS_LABELS } from "@/lib/logs";
import { applyRunStateEvent, runEventsUrl } from "@/lib/runStream";
import { formatDateTime } from "@/lib/time";
import type { ConfigFile, ConfigResponse, RunHistoryResponse, RunState, ScheduleConfig, ScheduleEntry, ScheduleResponse, SchedulesResponse, ScheduledRunSummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { LogPane } from "@/pages/main/LogPane";
import { ScheduleSettings, ScheduleStats } from "@/pages/schedule/ScheduleDetailPanels";
import { ScheduleLeftPane } from "@/pages/schedule/ScheduleLeftPane";

type CenterTab = "settings" | "stats";
const SCHEDULE_RUN_EVENTS_ERROR = "定时运行日志事件流连接中断，正在重连...";
const SCHEDULE_RETRY_COUNT_KEY = "maa-auto-panel:schedule-retry-count";

export function SchedulePage() {
  const { scheduleId } = useParams();
  const navigate = useNavigate();
  const [overview, setOverview] = React.useState<SchedulesResponse | null>(null);
  const [detail, setDetail] = React.useState<ScheduleResponse | null>(null);
  const [configs, setConfigs] = React.useState<ConfigFile[]>([]);
  const [draft, setDraft] = React.useState<ScheduleConfig | null>(null);
  const [draftTaskConfig, setDraftTaskConfig] = React.useState<ConfigResponse | null>(null);
  const [selectedEntryId, setSelectedEntryId] = React.useState("");
  const [globalRun, setGlobalRun] = React.useState<RunState>(() => idleRun());
  const [historyRun, setHistoryRun] = React.useState<RunState | null>(null);
  const [loadingHistoryRunId, setLoadingHistoryRunId] = React.useState("");
  const [newName, setNewName] = React.useState("日常定时");
  const [centerTab, setCenterTab] = React.useState<CenterTab>("settings");
  const [pendingTaskConfig, setPendingTaskConfig] = React.useState("");
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [runBusy, setRunBusy] = React.useState(false);
  const [retryCount, setRetryCount] = React.useState(() => readStoredCount(SCHEDULE_RETRY_COUNT_KEY, 1));
  const [error, setError] = React.useState("");
  const previousGlobalRunRef = React.useRef<RunState | null>(null);
  const refreshedRunIdRef = React.useRef("");

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
      setDraftTaskConfig(null);
      return;
    }
    readSchedule(scheduleId)
      .then((data) => {
        if (cancelled) return;
        setDetail(data);
        setDraft(cloneConfig(data.config));
        setDraftTaskConfig(null);
        setSelectedEntryId(data.config.entries[0]?.id || "");
        setHistoryRun(null);
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
    let cancelled = false;
    let events: EventSource | null = null;

    async function connectScheduleRunStream() {
      let snapshot: RunState | null = null;
      try {
        snapshot = await getCurrentScheduleRun();
        if (cancelled) return;
        setGlobalRun(snapshot);
        setError((current) => (current === SCHEDULE_RUN_EVENTS_ERROR ? "" : current));
      } catch (exc) {
        if (!cancelled) setError((current) => current || String(exc));
      }

      if (cancelled) return;
      events = new EventSource(runEventsUrl(currentScheduleRunEventsUrl, snapshot));
      events.onmessage = (event) => {
        setGlobalRun((current) => applyRunStateEvent(current, JSON.parse(event.data)));
        setError((current) => (current === SCHEDULE_RUN_EVENTS_ERROR ? "" : current));
      };
      events.onerror = () => {
        setError((current) => current || SCHEDULE_RUN_EVENTS_ERROR);
      };
    }

    void connectScheduleRunStream();
    return () => {
      cancelled = true;
      events?.close();
    };
  }, []);

  const dirty = Boolean(detail && draft && JSON.stringify(detail.config) !== JSON.stringify(draft));

  React.useEffect(() => {
    const previous = previousGlobalRunRef.current;
    previousGlobalRunRef.current = globalRun;
    const completed = completedScheduleRun(previous, globalRun);
    if (!completed || refreshedRunIdRef.current === completed.runId) return;

    refreshedRunIdRef.current = completed.runId;
    void refreshAfterScheduleRun(completed.scheduleId);
  }, [globalRun, scheduleId]);

  async function refreshOverview() {
    const data = await listSchedules();
    setOverview(data);
    return data;
  }

  async function refreshAfterScheduleRun(finishedScheduleId: string) {
    try {
      const overviewPromise = listSchedules();
      const detailPromise = finishedScheduleId === scheduleId ? readSchedule(finishedScheduleId) : null;
      const [overviewData, detailData] = await Promise.all([overviewPromise, detailPromise]);
      setOverview(overviewData);
      if (detailData) {
        setDetail((current) => (current?.config.id === detailData.config.id ? mergeScheduleRuntimeFields(current, detailData) : current));
      }
      setError((current) => (current === SCHEDULE_RUN_EVENTS_ERROR ? "" : current));
    } catch (exc) {
      setError((current) => current || String(exc));
    }
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
      setDraftTaskConfig(null);
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
    setDraftTaskConfig(null);
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
    setBusy(true);
    setError("");
    try {
      const taskConfig = await readTaskConfig(pendingTaskConfig);
      const taskIds = (taskConfig.task_items || []).map((item) => item.id);
      setDraft({
        ...draft,
        task_config: pendingTaskConfig,
        entries: draft.entries.map((entry) => ({ ...entry, task_ids: taskIds }))
      });
      setDraftTaskConfig(taskConfig);
      setPendingTaskConfig("");
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  async function handleStart() {
    const entryId = selectedEntryId || draft?.entries[0]?.id || "";
    if (!draft || runBusy || scheduleStartDisabledReason(globalRun, dirty, entryId)) return;
    setRunBusy(true);
    setError("");
    try {
      const startedRun = await startScheduleRun(draft.id, entryId, retryCount);
      setGlobalRun(startedRun);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setRunBusy(false);
    }
  }

  async function handleStop() {
    if (runBusy) return;
    setRunBusy(true);
    try {
      const stoppedRun = await stopCurrentScheduleRun();
      setGlobalRun(stoppedRun);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setRunBusy(false);
    }
  }

  async function handleForceStop() {
    if (runBusy) return;
    setRunBusy(true);
    try {
      const stoppedRun = await forceStopCurrentScheduleRun();
      setGlobalRun(stoppedRun);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setRunBusy(false);
    }
  }

  async function handleViewHistory(run: ScheduledRunSummary) {
    setLoadingHistoryRunId(run.id);
    setError("");
    try {
      const history = await getRunHistory(run.id);
      setHistoryRun(historyToRunState(history));
    } catch (exc) {
      setError(String(exc));
    } finally {
      setLoadingHistoryRunId("");
    }
  }

  async function handleDeleteHistory(run: ScheduledRunSummary) {
    setLoadingHistoryRunId(run.id);
    setError("");
    try {
      await deleteRunHistory(run.id);
      if (historyRun?.id === run.id) setHistoryRun(null);
      if (scheduleId) {
        const latest = await readSchedule(scheduleId);
        setDetail((current) => (current?.config.id === latest.config.id ? mergeScheduleRuntimeFields(current, latest) : current));
      }
      await refreshOverview();
    } catch (exc) {
      setError(String(exc));
    } finally {
      setLoadingHistoryRunId("");
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
                    <span className="text-muted-foreground">{stringMetadata(item.last_run, "entry_name")} · {formatDateTime(item.last_run.started_at)}</span>
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
  const taskItems = (draftTaskConfig || detail.task_config).task_items || [];
  const run = runForSchedule(globalRun, scheduleId);
  const startDisabledReason = scheduleStartDisabledReason(globalRun, dirty, selectedEntry?.id || "");
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
          <SegmentedControl
            value={centerTab}
            items={[
              { value: "settings", label: "设置", icon: <Settings2 className="size-4" /> },
              { value: "stats", label: "统计", icon: <BarChart3 className="size-4" /> }
            ]}
            onChange={setCenterTab}
          />
          <span className="min-w-0 whitespace-pre-line text-xs text-muted-foreground">{detail.timeline.message}</span>
        </div>
        <ScrollArea className="min-h-0">
          {centerTab === "settings" ? (
            <ScheduleSettings
              schedule={draft}
              detail={detail}
              onChange={setDraft}
            />
          ) : (
            <ScheduleStats
              detail={detail}
              selectedHistoryRunId={historyRun?.id}
              loadingHistoryRunId={loadingHistoryRunId}
              onViewHistory={handleViewHistory}
              onDeleteHistory={handleDeleteHistory}
            />
          )}
        </ScrollArea>
        <div className="grid grid-cols-[1fr_1fr_auto_auto] gap-2">
          <Button onClick={handleStart} disabled={runBusy || Boolean(startDisabledReason)} title={startDisabledReason || undefined}>
            <Play className="size-4" />
            运行当前时间点
          </Button>
          <RunStopButton run={run} busy={runBusy} onStop={handleStop} onForceStop={handleForceStop} />
          <label className="flex items-center justify-end gap-2">
            <span className="shrink-0 text-right text-[11px] leading-3 text-muted-foreground">重试<br />次数</span>
            <Input
              className="w-14 px-1 text-center text-sm"
              type="number"
              min={1}
              max={50}
              aria-label="重试次数"
              value={retryCount}
              onChange={(event) => {
                const next = clampRetryCount(event.target.value);
                setRetryCount(next);
                window.localStorage.setItem(SCHEDULE_RETRY_COUNT_KEY, String(next));
              }}
            />
          </label>
          <Button variant="outline" size="icon" aria-label="删除定时配置" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="size-4" />
          </Button>
        </div>
      </Card>

      <LogPane
        run={run}
        error={error}
        title="定时执行日志"
        emptyText="等待定时执行日志..."
        historyRun={historyRun}
        onCloseHistory={() => setHistoryRun(null)}
      />

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

function cloneConfig(config: ScheduleConfig): ScheduleConfig {
  return JSON.parse(JSON.stringify(config)) as ScheduleConfig;
}

function idleRun(): RunState {
  return { status: "idle", run: { status: "idle" }, retries: [] };
}

function historyToRunState(history: RunHistoryResponse): RunState {
  return {
    ...history.run,
    run: history.run,
    retries: history.retries || []
  };
}

function mergeScheduleRuntimeFields(current: ScheduleResponse, latest: ScheduleResponse): ScheduleResponse {
  return {
    ...current,
    file: latest.file,
    task_config: latest.task_config,
    task_policies: latest.task_policies,
    timeline: latest.timeline,
    daily_stats: latest.daily_stats,
    recent_runs: latest.recent_runs,
    scripts: latest.scripts,
    current_run: latest.current_run
  };
}

function runForSchedule(run: RunState, scheduleId?: string): RunState {
  return scheduleId && stringMetadata(run, "schedule_id") === scheduleId ? run : idleRun();
}

function isRunActive(run: RunState): boolean {
  return run.status === "running" || run.status === "stopping";
}

function completedScheduleRun(previous: RunState | null, current: RunState): { runId: string; scheduleId: string } | null {
  if (!previous || !isRunActive(previous) || isRunActive(current)) return null;
  const scheduleId = stringMetadata(previous, "schedule_id");
  if (!previous.id || !scheduleId) return null;
  if (current.id && current.id !== previous.id) return null;
  return { runId: previous.id, scheduleId };
}

function stringMetadata(run: { metadata?: Record<string, unknown> }, key: string): string {
  const value = run.metadata?.[key];
  return typeof value === "string" ? value : "";
}

function scheduleStartDisabledReason(globalRun: RunState, dirty: boolean, selectedEntryId: string): string {
  if (isRunActive(globalRun)) return "已有定时运行正在执行";
  if (dirty) return "请先保存或复位当前定时配置";
  if (!selectedEntryId) return "没有可运行的时间点";
  return "";
}

function sortEntriesByReset(entries: ScheduleEntry[], resetTime: string) {
  const reset = minutes(resetTime);
  return [...entries].sort((left, right) => ((minutes(left.time) - reset + 1440) % 1440) - ((minutes(right.time) - reset + 1440) % 1440));
}

function minutes(value: string) {
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}

function readStoredCount(key: string, fallback: number) {
  const value = Number(window.localStorage.getItem(key));
  return Number.isFinite(value) ? Math.min(50, Math.max(1, value)) : fallback;
}

function clampRetryCount(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(50, Math.max(1, parsed)) : 1;
}
