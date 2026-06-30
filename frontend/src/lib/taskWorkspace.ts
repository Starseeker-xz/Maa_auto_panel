import type { ConfigFile, ConfigResponse, TaskItem } from "@/lib/types";

export function normalizedConfigName(rawName: string) {
  const trimmed = rawName.trim().replace(/\.toml$/i, "");
  return trimmed || "new-task";
}

export function uniqueTaskConfigName(rawName: string, existing: ConfigFile[]) {
  const normalized = normalizedConfigName(rawName);
  const usedNames = new Set(existing.map((item) => item.name));
  if (!usedNames.has(normalized)) return normalized;

  const base = normalized;
  let suffix = 2;
  while (usedNames.has(`${base}-${suffix}`)) suffix += 1;
  return `${base}-${suffix}`;
}

export function localConfigFile(name: string): ConfigFile {
  const normalized = normalizedConfigName(name);
  const now = Date.now() / 1000;
  return {
    kind: "task",
    name: normalized,
    filename: `${normalized}.toml`,
    path: `config/maa/tasks/${normalized}.toml`,
    suffix: "toml",
    size: 0,
    modified_at: now
  };
}

export function localConfigResponse(file: ConfigFile, taskItems: TaskItem[], baseData: Record<string, unknown> = {}): ConfigResponse {
  return {
    file,
    content: "",
    data: { ...baseData, tasks: [] },
    task_items: taskItems,
    validation: { valid: true, errors: [] }
  };
}

export function withTaskItemIndexes(items: TaskItem[]) {
  return items.map((item, index) => ({ ...item, index: index + 1 }));
}

export function renameTaskItem(items: TaskItem[], itemId: string, name: string) {
  const nextName = name.trim();
  if (!nextName) return items;
  return items.map((item) => (item.id === itemId ? { ...item, name: nextName } : item));
}

export function deleteTaskItem(items: TaskItem[], itemId: string) {
  return withTaskItemIndexes(items.filter((item) => item.id !== itemId));
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
