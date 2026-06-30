import type { ConfigFile, ConfigResponse, TaskItem } from "@/lib/types";

export function normalizedConfigName(rawName: string) {
  const trimmed = rawName.trim();
  if (!trimmed) return "new-task.toml";
  return trimmed.endsWith(".toml") ? trimmed : `${trimmed}.toml`;
}

export function uniqueTaskConfigName(rawName: string, existing: ConfigFile[]) {
  const normalized = normalizedConfigName(rawName);
  const usedNames = new Set(existing.map((item) => item.name));
  if (!usedNames.has(normalized)) return normalized;

  const base = normalized.replace(/\.toml$/, "");
  let suffix = 2;
  while (usedNames.has(`${base}-${suffix}.toml`)) suffix += 1;
  return `${base}-${suffix}.toml`;
}

export function localConfigFile(name: string): ConfigFile {
  const now = Date.now() / 1000;
  return {
    kind: "task",
    name,
    filename: name,
    path: `config/maa/tasks/${name}`,
    suffix: ".toml",
    size: 0,
    modified_at: now
  };
}

export function localConfigResponse(file: ConfigFile, taskItems: TaskItem[]): ConfigResponse {
  return {
    file,
    content: "",
    data: { tasks: [] },
    task_items: taskItems,
    validation: { valid: true, errors: [] }
  };
}

export function reindexTaskItems(items: TaskItem[]) {
  return items.map((item, index) => ({ ...item, index }));
}

export function renameTaskItem(items: TaskItem[], itemId: string, name: string) {
  const nextName = name.trim();
  if (!nextName) return items;
  return items.map((item) => (item.id === itemId ? { ...item, name: nextName } : item));
}

export function deleteTaskItem(items: TaskItem[], itemId: string) {
  return reindexTaskItems(items.filter((item) => item.id !== itemId));
}

export function setTaskItemEnabled(items: TaskItem[], itemId: string, enabled: boolean) {
  return items.map((item) =>
    item.id === itemId
      ? {
          ...item,
          enabled,
          params: { ...item.params, enable: enabled }
        }
      : item
  );
}

export function setAllTaskItemsEnabled(items: TaskItem[], enabled: boolean) {
  return items.map((item) => ({
    ...item,
    enabled,
    params: { ...item.params, enable: enabled }
  }));
}

export function nextSelectedTaskItemIdAfterDelete(items: TaskItem[], deletedItemId: string) {
  const deletedIndex = items.findIndex((item) => item.id === deletedItemId);
  if (deletedIndex < 0 || items.length <= 1) return "";
  return items[Math.min(deletedIndex, items.length - 2)]?.id || "";
}
