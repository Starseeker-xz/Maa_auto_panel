import type { RunArrayPatch, RunRecord, RunRetry, RunState, RunStatePatchEvent } from "@/lib/types";

export function runEventsUrl(path: string, snapshot?: RunState | null) {
  const params = new URLSearchParams();
  if (typeof snapshot?.stream_version === "number") params.set("after", String(snapshot.stream_version));
  params.set("retries_from", String(snapshot?.retries?.length || 0));
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (timezone) params.set("client_timezone", timezone);
  params.set("client_offset_minutes", String(-new Date().getTimezoneOffset()));
  return `${path}?${params.toString()}`;
}

export function applyRunStateEvent(current: RunState, event: unknown): RunState {
  if (!isRecord(event)) return current;
  if (event.type === "patch") return applyPatchEvent(current, event as RunStatePatchEvent);
  if (event.type === "reset") {
    const { type: _type, ...state } = event as RunState & { type: "reset" };
    return normalizeRunState(state);
  }
  return normalizeRunState(event as RunState);
}

export function normalizeRunState(state: RunState): RunState {
  const nestedRun = isRecord(state.run) ? (state.run as RunRecord) : undefined;
  const run = nestedRun || state;
  if (run.status === "idle") return idleRunState(state.stream_version);
  const retries = asArray<RunRetry>(state.retries);
  return {
    ...run,
    run,
    retries,
    stream_version: state.stream_version
  };
}

function applyPatchEvent(current: RunState, event: RunStatePatchEvent): RunState {
  const state = event.state || {};
  const incomingRun = isRecord(state.run) ? (state.run as RunRecord) : undefined;
  const resetBase = shouldResetBase(current, incomingRun);
  const base = resetBase ? idleRunState() : current;
  const next: RunState = {
    ...base,
    ...(incomingRun || {}),
    run: incomingRun || base.run,
    stream_version: event.stream_version,
    retries: applyArrayPatch(base.retries || [], event.retries)
  };
  return normalizeRunState(next);
}

function shouldResetBase(current: RunState, incomingRun?: RunRecord) {
  if (incomingRun?.status === "idle") return true;
  if (incomingRun && "id" in incomingRun) return incomingRun.id !== current.id;
  return false;
}

function applyArrayPatch<T>(current: T[], patch?: RunArrayPatch<T>) {
  if (!patch) return current;
  const replaceFrom = Math.max(0, Math.min(patch.replace_from, current.length));
  return [...current.slice(0, replaceFrom), ...patch.items];
}

function idleRunState(streamVersion?: number): RunState {
  return { status: "idle", run: { status: "idle" }, retries: [], stream_version: streamVersion };
}

function asArray<T>(value: T[] | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
