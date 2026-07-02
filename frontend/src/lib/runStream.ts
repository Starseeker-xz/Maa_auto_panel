import type { MaaLogEntry, MaaTaskResult, RunArrayPatch, RunState, RunStatePatchEvent } from "@/lib/types";

export function runEventsUrl(path: string, snapshot?: RunState | null) {
  const params = new URLSearchParams();
  if (typeof snapshot?.stream_version === "number") params.set("after", String(snapshot.stream_version));
  params.set("output_from", String(snapshot?.output?.length || 0));
  params.set("task_results_from", String(snapshot?.task_results?.length || 0));
  params.set("log_entries_from", String(snapshot?.log_entries?.length || 0));
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

function applyPatchEvent(current: RunState, event: RunStatePatchEvent): RunState {
  const state = event.state || {};
  const resetBase = shouldResetBase(current, state);
  const base = resetBase ? idleRunState() : current;
  const next: RunState = {
    ...base,
    ...state,
    stream_version: event.stream_version
  };

  next.output = applyArrayPatch(base.output || [], event.output);
  next.task_results = applyArrayPatch(base.task_results || [], event.task_results);
  next.log_entries = applyArrayPatch(base.log_entries || [], event.log_entries);
  return normalizeRunState(next);
}

function shouldResetBase(current: RunState, state: Partial<RunState>) {
  if (state.status === "idle") return true;
  if ("id" in state) return state.id !== current.id;
  return false;
}

function applyArrayPatch<T>(current: T[], patch?: RunArrayPatch<T>) {
  if (!patch) return current;
  const replaceFrom = Math.max(0, Math.min(patch.replace_from, current.length));
  return [...current.slice(0, replaceFrom), ...patch.items];
}

function normalizeRunState(state: RunState): RunState {
  if (state.status === "idle") return idleRunState(state.stream_version);
  return {
    ...state,
    output: asArray<string>(state.output),
    task_results: asArray<MaaTaskResult>(state.task_results),
    log_entries: asArray<MaaLogEntry>(state.log_entries)
  };
}

function idleRunState(streamVersion?: number): RunState {
  return { status: "idle", stream_version: streamVersion, output: [], task_results: [], log_entries: [] };
}

function asArray<T>(value: T[] | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
