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
  linux_maa: {
    id?: string;
    check_after_completion?: boolean;
    [key: string]: unknown;
  };
};

export type ConfigsResponse = {
  config_root: string;
  profiles: ConfigFile[];
  tasks: ConfigFile[];
};

export type ConfigResponse = {
  file: ConfigFile;
  content: string;
  task_items?: TaskItem[];
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
