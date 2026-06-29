import React from "react";
import { useNavigate, useParams } from "react-router-dom";

import { getCurrentRun, listConfigs, readTaskConfig, startRun, stopRun } from "@/lib/api";
import { translateLogLine } from "@/lib/logs";
import type { ConfigsResponse, RunState, TaskItem } from "@/lib/types";
import { ConfigEditorPane } from "@/pages/main/ConfigEditorPane";
import { LogPane } from "@/pages/main/LogPane";
import { TaskListPane } from "@/pages/main/TaskListPane";

export function MainPage() {
  const navigate = useNavigate();
  const { taskConfig: taskConfigParam, taskItemId } = useParams();
  const routedTaskConfig = taskConfigParam ? decodeURIComponent(taskConfigParam) : "";
  const routedTaskItemId = taskItemId ? decodeURIComponent(taskItemId) : "";

  const [configs, setConfigs] = React.useState<ConfigsResponse | null>(null);
  const [taskConfig, setTaskConfig] = React.useState(routedTaskConfig);
  const [taskItems, setTaskItems] = React.useState<TaskItem[]>([]);
  const [run, setRun] = React.useState<RunState>({ status: "idle", output: [] });
  const [error, setError] = React.useState("");

  const profile = "default";
  const logText = React.useMemo(() => (run.output || []).map(translateLogLine).join(""), [run.output]);
  const selectedTaskItem = taskItems.find((item) => item.id === routedTaskItemId);

  React.useEffect(() => {
    setTaskConfig(routedTaskConfig);
  }, [routedTaskConfig]);

  const loadConfigs = React.useCallback(async () => {
    const data = await listConfigs();
    setConfigs(data);
    const nextTask = data.tasks.some((item) => item.name === taskConfig) ? taskConfig : data.tasks[0]?.name || "";
    setError("");

    if (!taskConfig && nextTask) {
      navigate(`/tasks/${encodeURIComponent(nextTask)}`, { replace: true });
      return;
    }

    setTaskConfig(nextTask);
  }, [navigate, taskConfig]);

  const loadTaskConfig = React.useCallback(async () => {
    if (!taskConfig) {
      setTaskItems([]);
      return;
    }
    const data = await readTaskConfig(taskConfig);
    setTaskItems(data.task_items || []);
  }, [taskConfig]);

  React.useEffect(() => {
    loadConfigs().catch((exc) => setError(String(exc)));
  }, []);

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

  return (
    <section className="grid min-h-screen grid-cols-[300px_minmax(420px,1fr)_360px] gap-4 p-4 max-xl:grid-cols-[285px_minmax(320px,1fr)] max-md:grid-cols-1 max-md:p-2">
      <TaskListPane
        taskConfigs={configs?.tasks || []}
        selectedTaskConfig={taskConfig}
        taskItems={taskItems}
        selectedTaskItemId={routedTaskItemId}
        run={run}
        onTaskConfigChange={handleTaskConfigChange}
        onStartRun={handleStartRun}
        onStopRun={handleStopRun}
      />
      <ConfigEditorPane taskConfig={taskConfig} selectedTaskItem={selectedTaskItem} />
      <LogPane run={run} logText={logText} error={error} />
    </section>
  );
}
