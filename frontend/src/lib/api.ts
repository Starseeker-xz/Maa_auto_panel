import type {
  ConfigResponse,
  ConfigsResponse,
  DeleteConfigResponse,
  MaaInfrastFilesResponse,
  MaaInfrastPlansResponse,
  MaaStagesResponse,
  MaintenanceActionState,
  RunState,
  SaveSettingsPayload,
  SaveTaskConfigPayload,
  SettingsResponse,
  UpdateInfoResponse
} from "@/lib/types";

async function readJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const text = await response.text();
  const data = text ? safeJsonParse(text) : null;
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? formatErrorDetail(data.detail) : text;
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

function formatErrorDetail(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String(detail.message);
  return JSON.stringify(detail);
}

export function listConfigs() {
  return readJson<ConfigsResponse>("/api/configs");
}

export function readTaskConfig(name: string) {
  return readJson<ConfigResponse>(`/api/configs/tasks/${encodeURIComponent(name)}`);
}

export function saveTaskConfig(name: string, payload: SaveTaskConfigPayload) {
  return readJson<ConfigResponse>(`/api/configs/tasks/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function deleteConfig(kind: string, name: string) {
  return readJson<DeleteConfigResponse>(`/api/configs/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export function getCurrentRun() {
  return readJson<RunState>("/api/runs/current");
}

export function startRun(payload: {
  task: string;
  profile: string;
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

export function getSettings() {
  return readJson<SettingsResponse>("/api/settings");
}

export function saveSettings(payload: SaveSettingsPayload) {
  return readJson<SettingsResponse>("/api/settings", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function getCurrentMaintenanceAction() {
  return readJson<MaintenanceActionState>("/api/maintenance/current");
}

export function getUpdateInfo() {
  return readJson<UpdateInfoResponse>("/api/maintenance/update-info");
}

export function startMaintenanceAction(kind: string) {
  return readJson<MaintenanceActionState>(`/api/maintenance/${encodeURIComponent(kind)}`, { method: "POST" });
}

export function getMaaStages(client = "Bilibili") {
  return readJson<MaaStagesResponse>(`/api/maa/stages?client=${encodeURIComponent(client)}`);
}

export function getInfrastPlanOptions(filename: string) {
  return readJson<MaaInfrastPlansResponse>(`/api/maa/infrast/plans?filename=${encodeURIComponent(filename)}`);
}

export function getInfrastFileOptions() {
  return readJson<MaaInfrastFilesResponse>("/api/maa/infrast/files");
}
