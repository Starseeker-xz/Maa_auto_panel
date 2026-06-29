import type { ConfigResponse, ConfigsResponse, RunState } from "@/lib/types";

async function readJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data as T;
}

export function listConfigs() {
  return readJson<ConfigsResponse>("/api/configs");
}

export function readTaskConfig(name: string) {
  return readJson<ConfigResponse>(`/api/configs/tasks/${encodeURIComponent(name)}`);
}

export function getCurrentRun() {
  return readJson<RunState>("/api/runs/current");
}

export function startRun(payload: {
  task: string;
  profile: string;
  attempts: number;
  timeout_seconds: number;
  log_level: number;
}) {
  return readJson<RunState>("/api/runs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function stopRun(runId: string) {
  return readJson<RunState>(`/api/runs/${runId}/stop`, { method: "POST" });
}
