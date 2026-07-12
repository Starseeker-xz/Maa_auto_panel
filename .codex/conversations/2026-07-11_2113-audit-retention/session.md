# Session 2026-07-11_2113-audit-retention

- Task: Read-only audit of run memory and history retention.
- Confirmed: `GenericRunManager._runs` and `_plans` receive every started run at manager.py:321-322 and have no removal path. Terminal `LiveRun` retains retries and bounded visible log structures; `RunStartPlan` retains callbacks/domain driver references.
- Confirmed: state indexes are bounded (`max_run_records=500`, `max_retry_records=2000`; store.py:15-18, 384-400), but `enforce_retention()` only rewrites those two indexes (81-85). Per-run history JSON written under `history/framework/runs` has no automatic prune.
- Confirmed: diagnostics do have a separate 14-day/count policy and are enforced at startup and each run completion (diagnostics.py:22-35,192-202; web/services.py:123-129; manager.py:870-871). Generated config directories are included.
- Confirmed: explicit history deletion removes the run/retry index entries and one history JSON only; it does not delete event logs, stdout/stderr logs, generated configs, MaaCore captures, or manager live state/plan (store.py:234-252).
- Current local sample (read-only): 63 indexed runs, 109 indexed retries, 63 history JSON files; no current orphan history because retention threshold has not been reached. This does not invalidate the structural leak.
- Recommendation: on terminal completion release `_plans[run_id]`; retain at most the active plus a small bounded terminal live snapshot (or serve terminal detail solely from store). Make run retention one coordinated policy that identifies evicted run IDs and deletes their history plus owned diagnostics/artifacts via explicit typed references. Preserve shared/non-owned artifacts. Add >limit lifecycle tests and manual-delete cascade semantics.
