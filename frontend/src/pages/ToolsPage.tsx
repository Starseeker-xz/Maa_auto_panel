import React from "react";

import { currentToolRunEventsUrl, forceStopCurrentToolRun, getCurrentToolRun, listTools, startToolRun, stopCurrentToolRun } from "@/lib/api";
import { applyRunStateEvent, normalizeRunState, runEventsUrl } from "@/lib/runStream";
import type { RunState, ToolDefinition } from "@/lib/types";
import { LogPane } from "@/pages/main/LogPane";
import { ToolConfigPane } from "@/pages/tools/ToolConfigPane";
import { ToolListPane } from "@/pages/tools/ToolListPane";

const TOOL_EVENTS_ERROR = "小工具日志事件流连接中断，正在重连...";
const TOOL_RETRY_COUNT_KEY = "linux-maa:tool-retry-count";

export function ToolsPage() {
  const [tools, setTools] = React.useState<ToolDefinition[]>([]);
  const [selectedToolId, setSelectedToolId] = React.useState("");
  const [configByTool, setConfigByTool] = React.useState<Record<string, Record<string, string>>>({});
  const [run, setRun] = React.useState<RunState>(() => idleRun());
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [retryCount, setRetryCount] = React.useState(() => readStoredCount(TOOL_RETRY_COUNT_KEY, 1));

  React.useEffect(() => {
    let cancelled = false;

    async function loadTools() {
      const data = await listTools();
      if (cancelled) return;
      setTools(data.tools);
      setSelectedToolId((current) => current || data.tools[0]?.id || "");
      setConfigByTool((current) => mergeDefaultConfigs(current, data.tools));
      setRun(data.current_run ? normalizeRunState(data.current_run) : idleRun());
      setError("");
    }

    loadTools().catch((exc) => {
      if (!cancelled) setError(String(exc));
    });

    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    let events: EventSource | null = null;

    async function connectToolRunStream() {
      let snapshot: RunState | null = null;
      try {
        snapshot = await getCurrentToolRun();
        if (cancelled) return;
        setRun(snapshot);
        setError((current) => (current === TOOL_EVENTS_ERROR ? "" : current));
      } catch (exc) {
        if (!cancelled) setError((current) => current || String(exc));
      }

      if (cancelled) return;
      events = new EventSource(runEventsUrl(currentToolRunEventsUrl, snapshot));
      events.onmessage = (event) => {
        setRun((current) => applyRunStateEvent(current, JSON.parse(event.data)));
        setError((current) => (current === TOOL_EVENTS_ERROR ? "" : current));
      };
      events.onerror = () => {
        setError((current) => current || TOOL_EVENTS_ERROR);
      };
    }

    void connectToolRunStream();
    return () => {
      cancelled = true;
      events?.close();
    };
  }, []);

  const selectedTool = tools.find((tool) => tool.id === selectedToolId);
  const selectedConfig = configByTool[selectedToolId] || {};
  const visibleRun = runForTool(run, selectedToolId);
  const activeToolId = isActiveRun(run) ? run.tool_id || "" : "";

  function handleConfigChange(fieldId: string, value: string) {
    setConfigByTool((current) => ({
      ...current,
      [selectedToolId]: {
        ...(current[selectedToolId] || {}),
        [fieldId]: value
      }
    }));
  }

  async function handleRun() {
    if (!selectedTool || busy) return;
    setBusy(true);
    setError("");
    try {
      const started = await startToolRun(selectedTool.id, selectedConfig, retryCount);
      setRun(started);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const stopped = await stopCurrentToolRun();
      setRun(stopped);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  async function handleForceStop() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const stopped = await forceStopCurrentToolRun();
      setRun(stopped);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="grid h-screen min-h-0 grid-cols-[270px_minmax(360px,1fr)_380px] gap-4 overflow-hidden p-4 max-xl:grid-cols-[270px_minmax(320px,1fr)] max-md:h-auto max-md:grid-cols-1 max-md:overflow-auto max-md:p-2">
      <ToolListPane tools={tools} selectedToolId={selectedToolId} activeToolId={activeToolId} onSelect={setSelectedToolId} />
      <ToolConfigPane
        tool={selectedTool}
        config={selectedConfig}
        run={visibleRun}
        busy={busy}
        onConfigChange={handleConfigChange}
        onRun={handleRun}
        onStop={handleStop}
        onForceStop={handleForceStop}
        retryCount={retryCount}
        onRetryCountChange={(value) => {
          setRetryCount(value);
          window.localStorage.setItem(TOOL_RETRY_COUNT_KEY, String(value));
        }}
      />
      <LogPane run={visibleRun} error={error} title="小工具日志" emptyText="等待小工具日志..." />
    </section>
  );
}

function mergeDefaultConfigs(current: Record<string, Record<string, string>>, tools: ToolDefinition[]) {
  const next = { ...current };
  for (const tool of tools) {
    if (next[tool.id]) continue;
    next[tool.id] = stringifyConfig(tool.default_config || {});
  }
  return next;
}

function stringifyConfig(config: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(config).map(([key, value]) => [key, value === undefined || value === null ? "" : String(value)]));
}

function runForTool(run: RunState, toolId: string): RunState {
  if (run.tool_id && toolId && run.tool_id !== toolId) return idleRun(run.stream_version);
  return run;
}

function isActiveRun(run: RunState) {
  return run.status === "running" || run.status === "stopping";
}

function idleRun(streamVersion?: number): RunState {
  return { status: "idle", run: { status: "idle" }, stream_version: streamVersion, retries: [] };
}

function readStoredCount(key: string, fallback: number) {
  const value = Number(window.localStorage.getItem(key));
  return Number.isFinite(value) ? Math.min(50, Math.max(1, value)) : fallback;
}
