import type {
  ConfigResponse,
  ConfigsResponse,
  DeleteConfigResponse,
  MaaInfrastFilesResponse,
  MaaInfrastPlansResponse,
  MaaStagesResponse,
  MaintenanceActionState,
  RunState,
  ScheduleResponse,
  SchedulesResponse,
  SaveSettingsPayload,
  SaveTaskConfigPayload,
  SettingsResponse,
  ToolsResponse,
  UpdateInfoResponse
} from "@/lib/types";

export const currentRunEventsUrl = "/api/runs/current/events";
export const currentScheduleRunEventsUrl = "/api/schedules/current/events";
export const currentToolRunEventsUrl = "/api/tools/current/events";

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
  if (Array.isArray(detail)) return detail.map(formatErrorItem).filter(Boolean).join("; ") || "请求参数错误";
  if (isRecord(detail) && "message" in detail) {
    const message = String(detail.message);
    const validation = formatValidationErrors(detail.validation);
    return validation ? `${message}: ${validation}` : message;
  }
  const formatted = formatErrorItem(detail);
  if (formatted) return formatted;
  return JSON.stringify(detail);
}

function formatValidationErrors(validation: unknown) {
  if (!isRecord(validation) || !Array.isArray(validation.errors)) return "";
  return validation.errors.map(formatErrorItem).filter(Boolean).join("; ");
}

function formatErrorItem(item: unknown) {
  if (!isRecord(item)) return item === undefined || item === null ? "" : String(item);
  const message = typeof item.msg === "string" ? item.msg : typeof item.message === "string" ? item.message : "";
  const loc = Array.isArray(item.loc) ? item.loc.join(".") : typeof item.path === "string" ? item.path : "";
  if (message && loc) return `${loc}: ${message}`;
  return message || (loc ? `${loc}: 参数错误` : "");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
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

export function listSchedules() {
  return readJson<SchedulesResponse>("/api/schedules");
}

export function createSchedule(payload: { name: string; task_config?: string }) {
  return readJson<ScheduleResponse>("/api/schedules", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function readSchedule(scheduleId: string) {
  return readJson<ScheduleResponse>(`/api/schedules/${encodeURIComponent(scheduleId)}`);
}

export function saveSchedule(scheduleId: string, config: Record<string, unknown>) {
  return readJson<ScheduleResponse>(`/api/schedules/${encodeURIComponent(scheduleId)}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ config })
  });
}

export function deleteSchedule(scheduleId: string) {
  return readJson<DeleteConfigResponse>(`/api/schedules/${encodeURIComponent(scheduleId)}`, { method: "DELETE" });
}

export function startScheduleRun(scheduleId: string, entryId?: string) {
  return readJson<RunState>(`/api/schedules/${encodeURIComponent(scheduleId)}/run`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ entry_id: entryId || null })
  });
}

export function getCurrentScheduleRun() {
  return readJson<RunState>("/api/schedules/current");
}

export function stopCurrentScheduleRun() {
  return readJson<RunState>("/api/schedules/current/stop", { method: "POST" });
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

export function listTools() {
  return readJson<ToolsResponse>("/api/tools");
}

export function getCurrentToolRun() {
  return readJson<RunState>("/api/tools/current");
}

export function startToolRun(toolId: string, config: Record<string, unknown>) {
  return readJson<RunState>(`/api/tools/${encodeURIComponent(toolId)}/run`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ config })
  });
}

export function stopCurrentToolRun() {
  return readJson<RunState>("/api/tools/current/stop", { method: "POST" });
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
