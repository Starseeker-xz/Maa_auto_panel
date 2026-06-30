export const DELETE_VALUE = Symbol("delete-value");
export type DeleteValue = typeof DELETE_VALUE;

export function stringAt(data: Record<string, unknown>, path: string[], fallback: string) {
  const value = valueAt(data, path);
  return typeof value === "string" ? value : fallback;
}

export function optionalNumberAt(data: Record<string, unknown>, path: string[]) {
  const value = valueAt(data, path);
  return typeof value === "number" ? value : "";
}

export function booleanAt(data: Record<string, unknown>, path: string[], fallback: boolean) {
  const value = valueAt(data, path);
  return typeof value === "boolean" ? value : fallback;
}

export function valueAt(data: Record<string, unknown>, path: string[]) {
  let current: unknown = data;
  for (const key of path) {
    if (!isRecord(current)) return undefined;
    current = current[key];
  }
  return current;
}

export function setNestedValue(data: Record<string, unknown>, path: string[], value: unknown | DeleteValue): Record<string, unknown> {
  const next = { ...data };
  let current: Record<string, unknown> = next;
  for (let index = 0; index < path.length - 1; index += 1) {
    const key = path[index];
    const existing = current[key];
    const child = isRecord(existing) ? { ...existing } : {};
    current[key] = child;
    current = child;
  }
  const lastKey = path[path.length - 1];
  if (value === DELETE_VALUE) {
    delete current[lastKey];
  } else {
    current[lastKey] = value;
  }
  return next;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
