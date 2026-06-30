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
    [key: string]: unknown;
  };
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
  attempts?: number;
  timeout_seconds?: number;
  log_level?: number;
  return_code?: number | null;
  log_file?: string | null;
  output?: string[];
};

export type Page = "main" | "schedule" | "settings";
