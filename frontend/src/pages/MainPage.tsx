import React from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DirtyActions } from "@/components/DirtyActions";
import { currentRunEventsUrl, deleteConfig, getCurrentRun, listConfigs, readTaskConfig, saveTaskConfig, startRun, stopRun } from "@/lib/api";
import { applyRunStateEvent, runEventsUrl } from "@/lib/runStream";
import { createTaskItem } from "@/lib/taskItemDefaults";
import {
  deleteTaskItem,
  localConfigFile,
  localConfigResponse,
  nextSelectedTaskItemIdAfterDelete,
  normalizedConfigName,
  renameTaskItem,
  setAllTaskItemsEnabled,
  setTaskItemEnabled,
  uniqueTaskConfigName,
  withTaskItemIndexes
} from "@/lib/taskWorkspace";
import type { ConfigFile, ConfigResponse, ConfigsResponse, RunState, TaskItem } from "@/lib/types";
import { ConfigEditorPane } from "@/pages/main/ConfigEditorPane";
import { LogPane } from "@/pages/main/LogPane";
import { TaskListPane } from "@/pages/main/TaskListPane";

type TaskConfigDraft = {
  file: ConfigFile;
  baseData: Record<string, unknown>;
  taskItems: TaskItem[];
  isNew: boolean;
};

type ConfirmAction = "delete" | null;

const DEFAULT_TASK_CONFIG_DATA = {
  "$schema": "../../../docs/maa-cli/schemas/task.schema.json"
};
const LAST_MAIN_PATH_KEY = "linux-maa:last-main-path";
const RUN_EVENTS_ERROR = "运行日志事件流连接中断，正在重连...";

export function MainPage() {
  const navigate = useNavigate();
  const { taskConfig: taskConfigParam, taskItemId } = useParams();
  const routedTaskConfig = taskConfigParam ? normalizedConfigName(decodeURIComponent(taskConfigParam)) : "";
  const routedTaskItemId = taskItemId ? decodeURIComponent(taskItemId) : "";

  const [configs, setConfigs] = React.useState<ConfigsResponse | null>(null);
  const [currentConfig, setCurrentConfig] = React.useState<ConfigResponse | null>(null);
  const [taskItems, setTaskItems] = React.useState<TaskItem[]>([]);
  const [draftsByConfig, setDraftsByConfig] = React.useState<Record<string, TaskConfigDraft>>({});
  const [run, setRun] = React.useState<RunState>({ status: "idle", output: [] });
  const [error, setError] = React.useState("");
  const [confirmAction, setConfirmAction] = React.useState<ConfirmAction>(null);
  const [actionBusy, setActionBusy] = React.useState(false);

  const profile = "default";
  const taskConfig = routedTaskConfig;
  const selectedTaskItem = taskItems.find((item) => item.id === routedTaskItemId);
  const taskConfigFiles = React.useMemo(() => {
    const savedFiles = configs?.tasks || [];
    const savedNames = new Set(savedFiles.map((item) => item.name));
    const draftFiles = Object.values(draftsByConfig)
      .filter((draft) => draft.isNew && !savedNames.has(draft.file.name))
      .map((draft) => draft.file);
    return [...savedFiles, ...draftFiles];
  }, [configs?.tasks, draftsByConfig]);
  const selectedConfigFile = React.useMemo(
    () => draftsByConfig[taskConfig]?.file || taskConfigFiles.find((item) => item.name === taskConfig) || localConfigFile(taskConfig),
    [draftsByConfig, taskConfig, taskConfigFiles]
  );
  const currentDraft = taskConfig ? draftsByConfig[taskConfig] : undefined;

  React.useEffect(() => {
    let cancelled = false;

    async function loadInitialConfigs() {
      const data = await listConfigs();
      if (cancelled) return;
      setConfigs(data);
      setError("");
    }

    loadInitialConfigs().catch((exc) => {
      if (!cancelled) setError(String(exc));
    });

    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    if (!configs) return;
    if (!taskConfig) {
      const firstTask = configs.tasks[0]?.name || "";
      if (firstTask) navigate(`/tasks/${encodeURIComponent(firstTask)}`, { replace: true });
      return;
    }

    const exists = configs.tasks.some((item) => item.name === taskConfig) || Boolean(draftsByConfig[taskConfig]);
    if (!exists) {
      const firstTask = configs.tasks[0]?.name || "";
      navigate(firstTask ? `/tasks/${encodeURIComponent(firstTask)}` : "/", { replace: true });
    }
  }, [configs, draftsByConfig, navigate, taskConfig]);

  React.useEffect(() => {
    if (!taskConfig) return;
    const path = routedTaskItemId
      ? `/tasks/${encodeURIComponent(taskConfig)}/items/${encodeURIComponent(routedTaskItemId)}`
      : `/tasks/${encodeURIComponent(taskConfig)}`;
    window.localStorage.setItem(LAST_MAIN_PATH_KEY, path);
  }, [routedTaskItemId, taskConfig]);

  React.useEffect(() => {
    let cancelled = false;

    async function loadTaskConfig() {
      if (!taskConfig) {
        setTaskItems([]);
        setCurrentConfig(null);
        return;
      }

      const draft = draftsByConfig[taskConfig];
      if (draft) {
        setTaskItems(draft.taskItems);
        setCurrentConfig(localConfigResponse(draft.file, draft.taskItems, draft.baseData));
        return;
      }

      const data = await readTaskConfig(taskConfig);
      if (cancelled) return;
      setCurrentConfig(data);
      setTaskItems(data.task_items || []);
    }

    loadTaskConfig().catch((exc) => {
      if (!cancelled) setError(String(exc));
    });

    return () => {
      cancelled = true;
    };
  }, [draftsByConfig, taskConfig]);

  React.useEffect(() => {
    let cancelled = false;
    let events: EventSource | null = null;

    async function connectRunStream() {
      let snapshot: RunState | null = null;
      try {
        snapshot = await getCurrentRun();
        if (cancelled) return;
        setRun(snapshot);
        setError((current) => (current === RUN_EVENTS_ERROR ? "" : current));
      } catch (exc) {
        if (!cancelled) setError((current) => current || String(exc));
      }

      if (cancelled) return;
      events = new EventSource(runEventsUrl(currentRunEventsUrl, snapshot));
      events.onmessage = (event) => {
        setRun((current) => applyRunStateEvent(current, JSON.parse(event.data)));
        setError((current) => (current === RUN_EVENTS_ERROR ? "" : current));
      };
      events.onerror = () => {
        setError((current) => current || RUN_EVENTS_ERROR);
      };
    }

    void connectRunStream();
    return () => {
      cancelled = true;
      events?.close();
    };
  }, []);

  function handleTaskConfigChange(name: string) {
    navigate(`/tasks/${encodeURIComponent(name)}`);
  }

  function handleTaskConfigCreate(rawName: string) {
    const name = uniqueTaskConfigName(rawName, taskConfigFiles);
    const file = localConfigFile(name);
    const draft = {
      file,
      baseData: DEFAULT_TASK_CONFIG_DATA,
      taskItems: [],
      isNew: true
    };
    setDraftsByConfig((current) => ({ ...current, [name]: draft }));
    setTaskItems([]);
    setCurrentConfig(localConfigResponse(file, [], draft.baseData));
    navigate(`/tasks/${encodeURIComponent(name)}`);
  }

  function commitTaskItems(updater: (items: TaskItem[]) => TaskItem[]) {
    if (!taskConfig) return;

    const existingDraft = draftsByConfig[taskConfig];
    const committed = withTaskItemIndexes(updater(taskItems));
    const baseData = existingDraft?.baseData || currentConfig?.data || {};
    const isNew = existingDraft?.isNew ?? !configs?.tasks.some((item) => item.name === taskConfig);
    const draft = {
      file: existingDraft?.file || selectedConfigFile,
      baseData,
      taskItems: committed,
      isNew: Boolean(isNew)
    };
    setTaskItems(committed);
    setDraftsByConfig((existing) => ({ ...existing, [taskConfig]: draft }));
    setCurrentConfig(localConfigResponse(draft.file, committed, baseData));
  }

  function handleTaskItemAdd(type: string) {
    if (!taskConfig) return;
    const nextItem = createTaskItem(type, taskItems);
    commitTaskItems((current) => [...current, nextItem]);
    navigate(`/tasks/${encodeURIComponent(taskConfig)}/items/${encodeURIComponent(nextItem.id)}`);
  }

  function handleTaskItemRename(itemId: string, name: string) {
    commitTaskItems((current) => renameTaskItem(current, itemId, name));
  }

  function handleTaskItemDelete(itemId: string) {
    const nextSelectedId = itemId === routedTaskItemId ? nextSelectedTaskItemIdAfterDelete(taskItems, itemId) : routedTaskItemId;
    commitTaskItems((current) => deleteTaskItem(current, itemId));
    if (itemId === routedTaskItemId) {
      const nextPath = nextSelectedId
        ? `/tasks/${encodeURIComponent(taskConfig)}/items/${encodeURIComponent(nextSelectedId)}`
        : `/tasks/${encodeURIComponent(taskConfig)}`;
      navigate(nextPath, { replace: true });
    }
  }

  function handleTaskItemUpdate(itemId: string, patch: Partial<Pick<TaskItem, "params" | "linux_maa">>) {
    commitTaskItems((current) => current.map((item) => (item.id === itemId ? { ...item, ...patch } : item)));
  }

  function handleTaskItemEnabledChange(itemId: string, enabled: boolean) {
    commitTaskItems((current) => setTaskItemEnabled(current, itemId, enabled));
  }

  function handleAllTaskItemsEnabledChange(enabled: boolean) {
    commitTaskItems((current) => setAllTaskItemsEnabled(current, enabled));
  }

  async function handleStartRun() {
    setError("");
    try {
      const data = await startRun({
        task: taskConfig,
        profile,
        log_level: 1
      });
      setRun(data);
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function handleStopRun() {
    if (!run.id) return;
    await stopRun(run.id);
  }

  function handleTaskItemsReorder(sourceId: string, targetIndex: number) {
    commitTaskItems((current) => {
      const sourceIndex = current.findIndex((item) => item.id === sourceId);
      if (sourceIndex < 0 || targetIndex < 0 || targetIndex > current.length) return current;
      const adjustedTargetIndex = targetIndex > sourceIndex ? targetIndex - 1 : targetIndex;
      if (sourceIndex === adjustedTargetIndex) return current;
      const next = [...current];
      const [moved] = next.splice(sourceIndex, 1);
      next.splice(adjustedTargetIndex, 0, moved);
      return next;
    });
  }

  async function refreshConfigs() {
    const data = await listConfigs();
    setConfigs(data);
    return data;
  }

  async function handleSaveDraft() {
    if (!taskConfig || !currentDraft) return;
    setActionBusy(true);
    setError("");
    try {
      const saved = await saveTaskConfig(taskConfig, {
        data: currentDraft.baseData,
        task_items: currentDraft.taskItems
      });
      setCurrentConfig(saved);
      setTaskItems(saved.task_items || []);
      setDraftsByConfig((existing) => omitDraft(existing, taskConfig));
      await refreshConfigs();
      if (saved.file.name !== taskConfig) {
        navigate(`/tasks/${encodeURIComponent(saved.file.name)}`, { replace: true });
      }
    } catch (exc) {
      setError(String(exc));
      throw exc;
    } finally {
      setActionBusy(false);
    }
  }

  async function handleResetDraft() {
    if (!taskConfig || !currentDraft) return;
    setActionBusy(true);
    setError("");
    try {
      setDraftsByConfig((existing) => omitDraft(existing, taskConfig));
      if (currentDraft.isNew) {
        const nextTask = configs?.tasks[0]?.name || "";
        setTaskItems([]);
        setCurrentConfig(null);
        navigate(nextTask ? `/tasks/${encodeURIComponent(nextTask)}` : "/", { replace: true });
        return;
      }

      const data = await readTaskConfig(taskConfig);
      setCurrentConfig(data);
      setTaskItems(data.task_items || []);
    } catch (exc) {
      setError(String(exc));
      throw exc;
    } finally {
      setActionBusy(false);
    }
  }

  async function handleDeleteTaskConfig() {
    if (!taskConfig) return;
    const deletingName = taskConfig;
    const deletingDraft = draftsByConfig[deletingName];
    setActionBusy(true);
    setError("");
    try {
      if (!deletingDraft?.isNew) {
        await deleteConfig("tasks", deletingName);
      }
      setDraftsByConfig((existing) => omitDraft(existing, deletingName));
      const data = deletingDraft?.isNew ? configs : await refreshConfigs();
      const nextTask = data?.tasks.find((item) => item.name !== deletingName)?.name || "";
      setTaskItems([]);
      setCurrentConfig(null);
      setConfirmAction(null);
      navigate(nextTask ? `/tasks/${encodeURIComponent(nextTask)}` : "/", { replace: true });
    } catch (exc) {
      setError(String(exc));
    } finally {
      setActionBusy(false);
    }
  }

  const dialog = deleteDialogContent(confirmAction, taskConfig);

  return (
    <section className="grid h-screen min-h-0 grid-cols-[300px_minmax(420px,1fr)_360px] gap-4 overflow-hidden p-4 max-xl:grid-cols-[285px_minmax(320px,1fr)] max-md:h-auto max-md:grid-cols-1 max-md:overflow-auto max-md:p-2">
      <TaskListPane
        taskConfigs={taskConfigFiles}
        selectedTaskConfig={taskConfig}
        taskItems={taskItems}
        selectedTaskItemId={routedTaskItemId}
        run={run}
        onTaskConfigChange={handleTaskConfigChange}
        onTaskConfigCreate={handleTaskConfigCreate}
        onTaskConfigDelete={() => setConfirmAction("delete")}
        onTaskItemAdd={handleTaskItemAdd}
        onTaskItemRename={handleTaskItemRename}
        onTaskItemDelete={handleTaskItemDelete}
        onTaskItemEnabledChange={handleTaskItemEnabledChange}
        onAllTaskItemsEnabledChange={handleAllTaskItemsEnabledChange}
        onTaskItemsReorder={handleTaskItemsReorder}
        onStartRun={handleStartRun}
        onStopRun={handleStopRun}
      />
      <ConfigEditorPane
        taskConfig={taskConfig}
        selectedTaskItem={selectedTaskItem}
        validation={currentConfig?.validation}
        onTaskItemUpdate={handleTaskItemUpdate}
      />
      <LogPane run={run} error={error} />
      <DirtyActions
        dirty={Boolean(currentDraft)}
        busy={actionBusy}
        saveTitle="保存配置修改"
        saveDescription={currentDraft ? `将当前修改写入 ${currentDraft.file.filename}。保存后，之后运行该任务配置会使用新的文件内容。` : ""}
        resetTitle="复位当前修改"
        resetDescription={currentDraft?.isNew ? "这个新配置尚未保存，复位会丢弃它。" : "复位会丢弃当前未保存修改，并重新载入磁盘上的配置。"}
        onSave={handleSaveDraft}
        onReset={handleResetDraft}
      />
      <ConfirmDialog
        open={Boolean(confirmAction && dialog)}
        title={dialog?.title || ""}
        description={dialog?.description || ""}
        confirmLabel={dialog?.confirmLabel || ""}
        tone={dialog?.tone}
        busy={actionBusy}
        onCancel={() => setConfirmAction(null)}
        onConfirm={() => {
          if (confirmAction === "delete") void handleDeleteTaskConfig();
        }}
      />
    </section>
  );
}

function omitDraft(drafts: Record<string, TaskConfigDraft>, name: string) {
  const next = { ...drafts };
  delete next[name];
  return next;
}

function deleteDialogContent(action: ConfirmAction, taskConfig: string) {
  if (action === "delete" && taskConfig) {
    return {
      title: "删除当前配置",
      description: `删除 ${taskConfig} 后，已保存的配置文件会移动到回收站；当前未保存修改也会被丢弃。`,
      confirmLabel: "删除",
      tone: "destructive" as const
    };
  }
  return null;
}
