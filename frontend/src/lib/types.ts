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

type ManagedParamItem = {
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

type ConfigValidationError = {
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
  tool_id?: string;
  tool_title?: string;
  schedule_id?: string;
  schedule_name?: string;
  entry_id?: string;
  entry_name?: string;
  task?: string;
  profile?: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  game_day?: string;
  trigger?: string;
  log_level?: number;
  return_code?: number | null;
  log_file?: string | null;
  log_files?: Record<string, string>;
  stream_version?: number;
  config?: Record<string, unknown>;
  output?: string[];
  task_results?: MaaTaskResult[];
  log_entries?: MaaLogEntry[];
};

export type RunArrayPatch<T> = {
  replace_from: number;
  items: T[];
};

export type RunStatePatchEvent = {
  type: "patch";
  stream_version?: number;
  state?: Partial<RunState>;
  output?: RunArrayPatch<string>;
  task_results?: RunArrayPatch<MaaTaskResult>;
  log_entries?: RunArrayPatch<MaaLogEntry>;
};

type SchedulerStatus = {
  enabled: boolean;
  status: string;
  current_run: RunState;
  recent_runs: ScheduledRunSummary[];
};

export type ScheduleConfigFile = {
  id: string;
  name: string;
  filename: string;
  path: string;
  size: number;
  modified_at: number;
  last_run?: ScheduledRunSummary | null;
};

export type ScheduleEntry = {
  id: string;
  name: string;
  time: string;
  enabled: boolean;
  task_ids: string[];
};

type ScheduleRetryPolicy = {
  max_attempts_per_group: number;
  group_buffer_seconds: number;
  max_groups: number;
};

type ScheduleTimeouts = {
  child_warning_seconds: number;
  child_danger_seconds: number;
  child_kill_seconds: number;
  run_warning_seconds: number;
  run_danger_seconds: number;
  run_kill_seconds: number;
};

type RestartScriptPolicy = {
  mode: "none" | "before_run" | "before_retry_group" | "before_retry";
  script: string;
  variables: Record<string, string>;
};

export type ScheduleConfig = {
  id: string;
  name: string;
  enabled: boolean;
  task_config: string;
  profile_name: string;
  profile: Record<string, unknown>;
  log_level: number;
  entries: ScheduleEntry[];
  retry: ScheduleRetryPolicy;
  timeouts: ScheduleTimeouts;
  restart: RestartScriptPolicy;
};

type TaskPolicy = {
  id: string;
  name: string;
  type: string;
  important: boolean;
  unlimited_runs: boolean;
  min_daily_successes: number;
  retry_even_success: boolean;
};

type DailyTaskStats = {
  task_id: string;
  task_name: string;
  successes: number;
  runs: number;
};

export type ScheduledRunSummary = {
  id: string;
  schedule_id: string;
  schedule_name: string;
  entry_id: string;
  entry_name: string;
  task_config: string;
  game_day: string;
  trigger: string;
  status: string;
  created_at: string;
  started_at?: string | null;
  ended_at?: string | null;
  attempt_count: number;
  retry_group_count: number;
  log_file?: string | null;
  log_files?: Record<string, string>;
  selected_task_ids: string[];
  summary: Record<string, unknown>;
};

type RunHistoryAttempt = {
  id: string;
  run_id: string;
  attempt_index: number;
  retry_group: number;
  status: string;
  started_at: string;
  ended_at: string;
  return_code?: number | null;
  task_ids: string[];
  task_results?: MaaTaskResult[];
  log_entries?: MaaLogEntry[];
  log_entries_file?: string;
  log_file?: string | null;
  log_files?: Record<string, string>;
  generated_config_dir?: string | null;
};

export type RunHistoryResponse = {
  run: RunState;
  attempts: RunHistoryAttempt[];
  events: Array<Record<string, unknown>>;
};

type ScriptVariable = {
  name: string;
  label: string;
  default: string;
};

type ScheduleScriptInfo = {
  name: string;
  path: string;
  variables: ScriptVariable[];
};

type ScheduleTimeline = {
  client: string;
  game_day: string;
  timezone_name: string;
  reset_local_time: string;
  order: string[];
  message: string;
  entries: ScheduleEntry[];
};

export type SchedulesResponse = {
  status: SchedulerStatus;
  schedules: ScheduleConfigFile[];
};

export type ScheduleResponse = {
  file: ConfigFile;
  config: ScheduleConfig;
  task_config: ConfigResponse;
  task_policies: TaskPolicy[];
  timeline: ScheduleTimeline;
  daily_stats: Record<string, DailyTaskStats>;
  recent_runs: ScheduledRunSummary[];
  scripts: ScheduleScriptInfo[];
  current_run: RunState;
};

export type MaaTaskResult = {
  type?: "task";
  name: string;
  task_id?: string;
  source_name?: string;
  status: MaaBlockStatus;
  rule_id?: string;
  panel_kind?: string;
  started_at?: string | null;
  ended_at?: string | null;
  messages?: MaaLogMessage[];
  lines: string[];
};

type MaaLogTone = "default" | "success" | "warning" | "danger" | "info" | "theme";
type MaaBlockStatus = "default" | "running" | "succeeded" | "failed" | "stopped" | "unknown" | "unfinished" | "warning";

type MaaLogSegment = {
  text: string;
  tone?: MaaLogTone;
  strong?: boolean;
};

type MaaLogImage = {
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
  metadata?: Record<string, unknown>;
};

export type MaaLogEntry = {
  type: "block";
  id: string;
  source: string;
  kind: string;
  title?: string;
  status?: MaaBlockStatus;
  time?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  tone?: MaaLogTone;
  messages?: MaaLogMessage[];
  lines: string[];
  raw?: string | null;
  metadata?: Record<string, unknown>;
  name?: string;
  task_id?: string;
  source_name?: string;
  rule_id?: string;
  panel_kind?: string;
};

export type SaveTaskConfigPayload = {
  data: Record<string, unknown>;
  task_items: TaskItem[];
};

type TrashRecord = {
  original_path: string;
  trash_path: string;
  deleted_at: string;
  size: number;
  label?: string;
};

export type DeleteConfigResponse = {
  deleted: TrashRecord;
};

type TimezoneInfo = {
  name: string;
  offset_minutes: number;
  label: string;
  resolved_at: string;
};

type FrameworkSettingsResponse = {
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
  log_file?: string | null;
  log_files?: Record<string, string>;
  output?: string[];
  task_results?: MaaTaskResult[];
  log_entries?: MaaLogEntry[];
};

type UpdateComponentInfo = {
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

type HotResourceUpdateInfo = {
  branch?: string;
  url?: string;
  local_commit?: string;
  remote_commit?: string;
  update_available?: boolean;
};

type LocalResourceVersionInfo = {
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

type ToolField = {
  id: string;
  label: string;
  kind: string;
  required?: boolean;
  placeholder?: string;
};

export type ToolDefinition = {
  id: string;
  title: string;
  description?: string;
  fields: ToolField[];
  default_config?: Record<string, unknown>;
};

export type ToolsResponse = {
  tools: ToolDefinition[];
  current_run: RunState;
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
