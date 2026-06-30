import type { ConfigResponse, ConfigsResponse, RunState } from "@/lib/types";

async function readJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const text = await response.text();
  const data = text ? safeJsonParse(text) : null;
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? String(data.detail) : text;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return data as T;
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
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
