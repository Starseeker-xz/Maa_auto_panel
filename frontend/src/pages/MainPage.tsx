import React from "react";
import { useNavigate, useParams } from "react-router-dom";

import { getCurrentRun, listConfigs, readTaskConfig, startRun, stopRun } from "@/lib/api";
import { translateLogLine } from "@/lib/logs";
import { createTaskItem } from "@/lib/taskItemDefaults";
import {
  deleteTaskItem,
  localConfigFile,
  localConfigResponse,
  nextSelectedTaskItemIdAfterDelete,
  reindexTaskItems,
  renameTaskItem,
  setAllTaskItemsEnabled,
  setTaskItemEnabled,
  uniqueTaskConfigName
} from "@/lib/taskWorkspace";
import type { ConfigFile, ConfigResponse, ConfigsResponse, RunState, TaskItem } from "@/lib/types";
import { ConfigEditorPane } from "@/pages/main/ConfigEditorPane";
import { LogPane } from "@/pages/main/LogPane";
import { TaskListPane } from "@/pages/main/TaskListPane";

export function MainPage() {
  const navigate = useNavigate();
  const { taskConfig: taskConfigParam, taskItemId } = useParams();
  const routedTaskConfig = taskConfigParam ? decodeURIComponent(taskConfigParam) : "";
  const routedTaskItemId = taskItemId ? decodeURIComponent(taskItemId) : "";
  const initialTaskConfig = React.useRef(routedTaskConfig);

  const [configs, setConfigs] = React.useState<ConfigsResponse | null>(null);
  const [currentConfig, setCurrentConfig] = React.useState<ConfigResponse | null>(null);
  const [taskConfig, setTaskConfig] = React.useState(routedTaskConfig);
  const [taskItems, setTaskItems] = React.useState<TaskItem[]>([]);
  const [localTaskConfigs, setLocalTaskConfigs] = React.useState<ConfigFile[]>([]);
  const [localTaskItemsByConfig, setLocalTaskItemsByConfig] = React.useState<Record<string, TaskItem[]>>({});
  const [run, setRun] = React.useState<RunState>({ status: "idle", output: [] });
  const [error, setError] = React.useState("");

  const profile = "default";
  const logText = React.useMemo(() => (run.output || []).map(translateLogLine).join(""), [run.output]);
  const selectedTaskItem = taskItems.find((item) => item.id === routedTaskItemId);
  const taskConfigFiles = React.useMemo(() => [...(configs?.tasks || []), ...localTaskConfigs], [configs?.tasks, localTaskConfigs]);
  const selectedConfigFile = React.useMemo(
    () => taskConfigFiles.find((item) => item.name === taskConfig) || localConfigFile(taskConfig),
    [taskConfig, taskConfigFiles]
  );

  React.useEffect(() => {
    setTaskConfig(routedTaskConfig);
  }, [routedTaskConfig]);

  const loadTaskConfig = React.useCallback(async () => {
    if (!taskConfig) {
      setTaskItems([]);
      setCurrentConfig(null);
      return;
    }
    if (Object.prototype.hasOwnProperty.call(localTaskItemsByConfig, taskConfig)) {
      const localItems = localTaskItemsByConfig[taskConfig] || [];
      setTaskItems(localItems);
      setCurrentConfig(localConfigResponse(localConfigFile(taskConfig), localItems));
      return;
    }
    const data = await readTaskConfig(taskConfig);
    setCurrentConfig(data);
    setTaskItems(data.task_items || []);
  }, [localTaskItemsByConfig, taskConfig]);

  React.useEffect(() => {
    let cancelled = false;

    async function loadInitialConfigs() {
      const data = await listConfigs();
      if (cancelled) return;

      setConfigs(data);
      setError("");

      const requestedTask = initialTaskConfig.current;
      const requestedExists = data.tasks.some((item) => item.name === requestedTask);
      const nextTask = requestedExists ? requestedTask : data.tasks[0]?.name || "";
      setTaskConfig(nextTask);

      if (nextTask && requestedTask !== nextTask) {
        navigate(`/tasks/${encodeURIComponent(nextTask)}`, { replace: true });
      }
    }

    loadInitialConfigs().catch((exc) => {
      if (!cancelled) setError(String(exc));
    });

    return () => {
      cancelled = true;
    };
  }, [navigate]);

  React.useEffect(() => {
    loadTaskConfig().catch((exc) => setError(String(exc)));
  }, [loadTaskConfig]);

  React.useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const data = await getCurrentRun();
        setRun(data);
      } catch (exc) {
        setError(String(exc));
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  function handleTaskConfigChange(name: string) {
    navigate(`/tasks/${encodeURIComponent(name)}`);
  }

  function handleTaskConfigCreate(rawName: string) {
    const name = uniqueTaskConfigName(rawName, taskConfigFiles);
    const file = localConfigFile(name);
    setLocalTaskConfigs((current) => [...current, file]);
    setLocalTaskItemsByConfig((current) => ({ ...current, [name]: [] }));
    setTaskItems([]);
    setCurrentConfig(localConfigResponse(file, []));
    navigate(`/tasks/${encodeURIComponent(name)}`);
  }

  function commitTaskItems(updater: (items: TaskItem[]) => TaskItem[]) {
    if (!taskConfig) return;

    setTaskItems((current) => {
      const committed = reindexTaskItems(updater(current));
      setLocalTaskItemsByConfig((existing) => ({ ...existing, [taskConfig]: committed }));
      setCurrentConfig(localConfigResponse(selectedConfigFile, committed));
      return committed;
    });
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
        attempts: 1,
        timeout_seconds: 900,
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
      <LogPane run={run} logText={logText} error={error} />
    </section>
  );
}
