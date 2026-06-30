export type ConfigFile = {
  kind: string;
  name: string;
  filename: string;
  path: string;
  suffix: string;
  size: number;
  modified_at: number;
};

export type TaskItem = {
  id: string;
  index: number;
  name: string;
  type: string;
  enabled: boolean;
  strategy?: unknown;
  params: Record<string, unknown>;
  variants: unknown[];
  linux_maa: {
    id?: string;
    unlimited_runs?: boolean;
    min_daily_successes?: number;
    important?: boolean;
    retry_even_success?: boolean;
    managed_params?: Record<string, ManagedParamSpec>;
    [key: string]: unknown;
  };
};

export type ManagedParamItem = {
  value: unknown;
  enabled?: boolean;
};

export type ManagedParamSpec = {
  type?: "array" | "runtime";
  handler?: string;
  value?: unknown;
  items?: ManagedParamItem[];
  [key: string]: unknown;
};

export type ConfigValidationError = {
  path: string;
  message: string;
  source: string;
};

export type ConfigValidation = {
  valid: boolean;
  errors: ConfigValidationError[];
};

export type ConfigsResponse = {
  config_root: string;
  profiles: ConfigFile[];
  tasks: ConfigFile[];
};

export type ConfigResponse = {
  file: ConfigFile;
  content: string;
  data?: Record<string, unknown>;
  task_items?: TaskItem[];
  validation?: ConfigValidation;
  metadata_schema?: Record<string, unknown>;
};

export type RunState = {
  id?: string;
  task?: string;
  profile?: string;
  status: string;
  log_level?: number;
  return_code?: number | null;
  log_file?: string | null;
  output?: string[];
  task_results?: MaaTaskResult[];
  log_entries?: MaaLogEntry[];
};

export type MaaTaskResult = {
  type?: "task";
  name: string;
  status: "running" | "succeeded" | "failed" | "stopped" | "unknown";
  rule_id?: string;
  panel_kind?: string;
  started_at?: string | null;
  ended_at?: string | null;
  messages?: MaaLogMessage[];
  lines: string[];
};

export type MaaLogTone = "default" | "success" | "warning" | "danger" | "info";

export type MaaLogSegment = {
  text: string;
  tone?: MaaLogTone;
  strong?: boolean;
};

export type MaaLogImage = {
  src: string;
  alt?: string;
  width?: number;
  height?: number;
};

export type MaaLogMessage = {
  type?: "text" | "image";
  text: string;
  time?: string | null;
  tone?: MaaLogTone;
  raw?: string | null;
  segments?: MaaLogSegment[];
  image?: MaaLogImage | null;
};

export type MaaLogLineEntry = Omit<MaaLogMessage, "type"> & {
  type: "line";
};

export type MaaLogTaskEntry = MaaTaskResult & {
  type: "task";
};

export type MaaLogEntry = MaaLogLineEntry | MaaLogTaskEntry;

export type SaveTaskConfigPayload = {
  data: Record<string, unknown>;
  task_items: TaskItem[];
};

export type TrashRecord = {
  original_path: string;
  trash_path: string;
  deleted_at: string;
  size: number;
  label?: string;
};

export type DeleteConfigResponse = {
  deleted: TrashRecord;
};

export type TimezoneInfo = {
  name: string;
  offset_minutes: number;
  label: string;
  resolved_at: string;
};

export type FrameworkSettingsResponse = {
  file: {
    path: string;
    exists: boolean;
  };
  data: Record<string, unknown>;
  effective_timezone: TimezoneInfo;
};

export type MaintenanceActionState = {
  id?: string;
  kind?: string;
  title?: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  return_code?: number | null;
  output?: string[];
};

export type UpdateComponentInfo = {
  channel?: string;
  api_url?: string;
  version?: string;
  published_at?: string;
  html_url?: string;
  tag?: string;
  commit?: string;
  update_available?: boolean;
  [key: string]: unknown;
};

export type HotResourceUpdateInfo = {
  branch?: string;
  url?: string;
  local_commit?: string;
  remote_commit?: string;
  update_available?: boolean;
};

export type LocalResourceVersionInfo = {
  exists?: boolean;
  name?: string;
  last_updated?: string;
  path?: string;
  error?: string;
};

export type UpdateInfoResponse = {
  checked_at: string;
  current: {
    maa_cli?: string;
    maa_core?: string;
    base_resource?: LocalResourceVersionInfo;
    hot_resource?: LocalResourceVersionInfo;
    [key: string]: unknown;
  };
  latest: {
    maa_core?: UpdateComponentInfo;
    maa_cli?: UpdateComponentInfo;
    hot_resource?: HotResourceUpdateInfo;
  };
  errors: string[];
};

export type SettingsResponse = {
  framework: FrameworkSettingsResponse;
  profile: ConfigResponse;
  maa_cli: ConfigResponse;
  maintenance: MaintenanceActionState;
};

export type DynamicOption = {
  value: string | number | boolean | null;
  label: string;
  [key: string]: unknown;
};

export type MaaStagesResponse = {
  client: string;
  effective_client: string;
  checked_at: string;
  stages: Array<{
    value: string;
    display: string;
    is_open: boolean;
    [key: string]: unknown;
  }>;
  errors: string[];
};

export type MaaInfrastPlansResponse = {
  filename: string;
  checked_at: string;
  options: DynamicOption[];
  errors: string[];
};

export type MaaInfrastFilesResponse = {
  directory: string;
  options: DynamicOption[];
  errors: string[];
};

export type SaveSettingsPayload = {
  framework: Record<string, unknown>;
  profile: Record<string, unknown>;
  maa_cli: Record<string, unknown>;
};

export type Page = "main" | "schedule" | "settings";
