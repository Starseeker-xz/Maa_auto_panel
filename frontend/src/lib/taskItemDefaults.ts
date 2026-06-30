import defaults from "@/config/task-item-defaults.json";
import type { TaskItem } from "@/lib/types";

export type TaskItemDefault = {
  type: string;
  name: string;
  params: Record<string, unknown>;
  linux_maa?: Record<string, unknown>;
};

export const taskItemDefaults = defaults as TaskItemDefault[];

export function createTaskItem(type: string, currentItems: TaskItem[]): TaskItem {
  const template = taskItemDefaults.find((item) => item.type === type) || taskItemDefaults[0];
  const index = currentItems.length + 1;
  const duplicateCount = currentItems.filter((item) => item.type === template.type).length;
  const name = duplicateCount > 0 ? `${template.name} ${duplicateCount + 1}` : template.name;
  const idBase = slug(`${template.type}-${name}`);
  const id = uniqueId(idBase, currentItems);

  return {
    id,
    index,
    name,
    type: template.type,
    enabled: true,
    params: { ...structuredClone(template.params), enable: true },
    variants: [],
    linux_maa: {
      id,
      unlimited_runs: true,
      important: true,
      ...(template.linux_maa ? structuredClone(template.linux_maa) : {})
    }
  };
}

function uniqueId(base: string, currentItems: TaskItem[]) {
  const usedIds = new Set(currentItems.map((item) => item.id));
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const candidate = `${base}-${randomHexSuffix()}`;
    if (!usedIds.has(candidate)) return candidate;
  }

  let suffix = 2;
  while (usedIds.has(`${base}-${suffix}`)) suffix += 1;
  return `${base}-${suffix}`;
}

function slug(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_.-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 56) || "task";
}

function randomHexSuffix() {
  const bytes = new Uint8Array(4);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}
