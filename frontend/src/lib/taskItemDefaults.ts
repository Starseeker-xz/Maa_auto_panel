import defaults from "@/config/task-item-defaults.json";
import type { TaskItem } from "@/lib/types";

export type TaskItemDefault = {
  type: string;
  name: string;
  params: Record<string, unknown>;
};

export const taskItemDefaults = defaults as TaskItemDefault[];

export function createTaskItem(type: string, currentItems: TaskItem[]): TaskItem {
  const template = taskItemDefaults.find((item) => item.type === type) || taskItemDefaults[0];
  const index = currentItems.length;
  const duplicateCount = currentItems.filter((item) => item.type === template.type).length;
  const name = duplicateCount > 0 ? `${template.name} ${duplicateCount + 1}` : template.name;
  const idBase = template.type.toLowerCase().replace(/[^a-z0-9]+/g, "-");
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
      important: true
    }
  };
}

function uniqueId(base: string, currentItems: TaskItem[]) {
  const usedIds = new Set(currentItems.map((item) => item.id));
  if (!usedIds.has(base)) return base;

  let suffix = 2;
  while (usedIds.has(`${base}-${suffix}`)) suffix += 1;
  return `${base}-${suffix}`;
}
