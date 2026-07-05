export function formatTimeOfDay(value?: string | null) {
  const parsed = parseBackendTime(value);
  if (!parsed) return value || "";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(parsed);
}

export function formatDateTime(value?: string | null) {
  const parsed = parseBackendTime(value);
  if (!parsed) return value || "";
  return new Intl.DateTimeFormat(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(parsed);
}

function parseBackendTime(value?: string | null) {
  if (!value) return null;
  const text = value.trim();
  if (!text) return null;
  if (/^\d{2}:\d{2}:\d{2}$/.test(text)) return null;
  const normalized = normalizeBackendDateTime(text);
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function normalizeBackendDateTime(value: string) {
  if (/[zZ]$|[+-]\d{2}:\d{2}$/.test(value)) return value;
  if (/^\d{4}-\d{2}-\d{2}T/.test(value)) return `${value}Z`;
  if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}/.test(value)) return `${value.replace(" ", "T")}Z`;
  return value;
}
