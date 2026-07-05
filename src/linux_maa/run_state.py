from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from linux_maa.maa.runtime import MaaRuntime
from linux_maa.storage.files import read_json_object, write_json_object
from linux_maa.time_utils import server_now_iso
from linux_maa.utils import relative_path, slugify


RunKind = Literal["manual", "schedule", "maintenance", "tool"]


@dataclass(frozen=True)
class StateRetentionPolicy:
    max_run_records: int = 500
    max_retry_records: int = 2000
    max_trigger_records: int = 2000
    max_scheduler_state_days: int = 90


@dataclass(frozen=True)
class StoredRun:
    id: str
    kind: RunKind
    status: str
    title: str
    started_at: str
    updated_at: str | None = None
    ended_at: str | None = None
    return_code: int | None = None
    max_retries: int = 1
    retry_count: int = 0
    retry_group_count: int = 0
    log_files: dict[str, str] = field(default_factory=dict)
    event_log_file: str | None = None
    maacore_log_file: str | None = None
    generated_config_dir: str | None = None
    selected_task_ids: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    schedule_id: str = ""
    schedule_name: str = ""
    entry_id: str = ""
    entry_name: str = ""
    task_config: str = ""
    game_day: str = ""
    trigger: str = ""
    task: str = ""
    profile: str = ""
    maintenance_kind: str = ""
    tool_id: str = ""
    tool_title: str = ""

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "title": self.title,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "ended_at": self.ended_at,
            "return_code": self.return_code,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "retry_group_count": self.retry_group_count,
            "log_files": dict(self.log_files),
            "event_log_file": self.event_log_file,
            "maacore_log_file": self.maacore_log_file,
            "generated_config_dir": self.generated_config_dir,
            "selected_task_ids": list(self.selected_task_ids),
            "summary": dict(self.summary),
        }
        optional = {
            "schedule_id": self.schedule_id,
            "schedule_name": self.schedule_name,
            "entry_id": self.entry_id,
            "entry_name": self.entry_name,
            "task_config": self.task_config,
            "game_day": self.game_day,
            "trigger": self.trigger,
            "task": self.task,
            "profile": self.profile,
            "maintenance_kind": self.maintenance_kind,
            "tool_id": self.tool_id,
            "tool_title": self.tool_title,
        }
        data.update({key: value for key, value in optional.items() if value})
        return data


class RunStateStore:
    def __init__(self, runtime: MaaRuntime, retention: StateRetentionPolicy | None = None) -> None:
        self.runtime = runtime
        self.retention = retention or StateRetentionPolicy()
        self._lock = threading.RLock()
        self.ensure_dirs()

    @property
    def run_records_path(self) -> Path:
        return self.runtime.run_state_dir / "recent-run-records.json"

    @property
    def retries_path(self) -> Path:
        return self.runtime.run_state_dir / "run-retries.json"

    @property
    def triggers_path(self) -> Path:
        return self.runtime.scheduler_state_dir / "triggered-schedule-entries.json"

    @property
    def daily_stats_path(self) -> Path:
        return self.runtime.scheduler_state_dir / "daily-task-stats.json"

    def ensure_dirs(self) -> None:
        self.runtime.run_state_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.scheduler_state_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.run_history_dir.mkdir(parents=True, exist_ok=True)

    def enforce_retention(self) -> None:
        with self._lock:
            self._write_runs(self.runs(limit=0))
            retries = self._retry_items()[-self.retention.max_retry_records :]
            self._write_retries(retries)
            triggers = self._trigger_items()[-self.retention.max_trigger_records :]
            self._write_triggers(triggers)
            self._prune_daily_stats()

    def recover_interrupted_runs(self) -> int:
        recovered = 0
        for item in self._run_items():
            run_id = str(item.get("id") or "")
            if not run_id or item.get("status") not in {"running", "stopping"}:
                continue
            summary = dict(item.get("summary")) if isinstance(item.get("summary"), dict) else {}
            summary["recovered_status"] = str(item.get("status") or "running")
            summary["recovered_reason"] = "backend restarted before run finalized"
            self._upsert_run({"id": run_id, "status": "stopped", "ended_at": _now(), "updated_at": _now(), "summary": summary})
            self._sync_run_history(run_id)
            recovered += 1
        return recovered

    def create_run(
        self,
        *,
        run_id: str,
        kind: RunKind,
        title: str,
        max_retries: int = 1,
        log_files: dict[str, str] | None = None,
        event_log_file: str | None = None,
        selected_task_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        started_at = _now()
        data: dict[str, object] = {
            "id": run_id,
            "kind": kind,
            "status": "running",
            "title": title,
            "started_at": started_at,
            "updated_at": started_at,
            "max_retries": max(1, max_retries),
            "log_files": log_files or {},
            "event_log_file": event_log_file,
            "selected_task_ids": selected_task_ids or [],
        }
        if metadata:
            data.update(metadata)
        self._upsert_run(data)

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        return_code: int | None = None,
        retry_count: int | None = None,
        retry_group_count: int | None = None,
        summary: dict[str, Any] | None = None,
        maacore_log_file: str | None = None,
        generated_config_dir: str | None = None,
    ) -> None:
        patch: dict[str, object] = {
            "id": run_id,
            "status": status,
            "ended_at": _now(),
            "updated_at": _now(),
            "return_code": return_code,
        }
        if retry_count is not None:
            patch["retry_count"] = retry_count
        if retry_group_count is not None:
            patch["retry_group_count"] = retry_group_count
        if summary is not None:
            patch["summary"] = summary
        if maacore_log_file is not None:
            patch["maacore_log_file"] = maacore_log_file
        if generated_config_dir is not None:
            patch["generated_config_dir"] = generated_config_dir
        self._upsert_run(patch)
        self._sync_run_history(run_id)

    def add_retry(
        self,
        *,
        retry_id: str,
        run_id: str,
        retry_index: int,
        retry_group: int,
        status: str,
        started_at: str,
        updated_at: str,
        ended_at: str,
        return_code: int | None,
        task_ids: list[str],
        task_results: list[dict[str, Any]],
        log_entries: list[dict[str, Any]],
        log_files: dict[str, str] | None = None,
        generated_config_dir: str | None = None,
        maacore_log_file: str | None = None,
    ) -> None:
        with self._lock:
            history_file = self._write_retry_history(
                run_id=run_id,
                retry_id=retry_id,
                retry_index=retry_index,
                retry_group=retry_group,
                status=status,
                started_at=started_at,
                updated_at=updated_at,
                ended_at=ended_at,
                return_code=return_code,
                task_ids=task_ids,
                task_results=task_results,
                log_entries=log_entries,
                log_files=log_files,
                generated_config_dir=generated_config_dir,
                maacore_log_file=maacore_log_file,
            )
            retries = [item for item in self._retry_items() if item.get("id") != retry_id]
            retries.append(
                {
                    "id": retry_id,
                    "run_id": run_id,
                    "retry_index": retry_index,
                    "retry_group": retry_group,
                    "status": status,
                    "started_at": started_at,
                    "updated_at": updated_at,
                    "ended_at": ended_at,
                    "return_code": return_code,
                    "task_ids": task_ids,
                    "task_results": task_results,
                    "log_entries_file": history_file,
                    "log_files": log_files or {},
                    "generated_config_dir": generated_config_dir,
                    "maacore_log_file": maacore_log_file,
                }
            )
            self._write_retries(retries[-self.retention.max_retry_records :])

    def daily_stats(self, schedule_id: str, game_day: str) -> dict[str, object]:
        from linux_maa.scheduler.models import DailyTaskStats

        data = self._daily_stats_data()
        schedules = _dict_value(data.get("schedules"))
        days = _dict_value(_dict_value(schedules.get(schedule_id)).get("days"))
        raw_stats = _dict_value(_dict_value(days.get(game_day)).get("tasks"))
        output: dict[str, DailyTaskStats] = {}
        for task_id, item in raw_stats.items():
            if isinstance(item, dict):
                output[str(task_id)] = DailyTaskStats(
                    task_id=str(task_id),
                    task_name=str(item.get("task_name") or task_id),
                    successes=_int_value(item.get("successes")),
                    runs=_int_value(item.get("runs")),
                )
        return output

    def update_daily_stats(
        self,
        *,
        schedule_id: str,
        game_day: str,
        task_names: dict[str, str],
        task_statuses: dict[str, str],
    ) -> None:
        with self._lock:
            data = self._daily_stats_data()
            schedules = data.setdefault("schedules", {})
            by_schedule = schedules.setdefault(schedule_id, {"days": {}})
            days = by_schedule.setdefault("days", {})
            day = days.setdefault(game_day, {"tasks": {}})
            tasks = day.setdefault("tasks", {})
            for task_id, task_name in task_names.items():
                current = tasks.setdefault(task_id, {"task_id": task_id, "task_name": task_name, "successes": 0, "runs": 0})
                current["task_name"] = task_name
                current["successes"] = _int_value(current.get("successes")) + (1 if task_statuses.get(task_id) == "succeeded" else 0)
                current["runs"] = _int_value(current.get("runs")) + 1
                current["updated_at"] = _now()
            day["updated_at"] = _now()
            data["updated_at"] = _now()
            self._write_daily_stats(data)

    def mark_triggered(self, *, schedule_id: str, entry_id: str, game_day: str, run_id: str) -> None:
        with self._lock:
            if self.already_triggered(schedule_id=schedule_id, entry_id=entry_id, game_day=game_day):
                return
            triggers = self._trigger_items()
            triggers.append(
                {
                    "schedule_id": schedule_id,
                    "entry_id": entry_id,
                    "game_day": game_day,
                    "run_id": run_id,
                    "ran_at": _now(),
                }
            )
            self._write_triggers(triggers[-self.retention.max_trigger_records :])

    def already_triggered(self, *, schedule_id: str, entry_id: str, game_day: str) -> bool:
        for item in self._trigger_items():
            if item.get("schedule_id") == schedule_id and item.get("entry_id") == entry_id and item.get("game_day") == game_day:
                return True
        return False

    def recent_runs(self, schedule_id: str | None = None, *, limit: int = 20) -> list[StoredRun]:
        runs = [
            run
            for run in self.runs(kind="schedule", limit=0)
            if schedule_id is None or run.schedule_id == schedule_id
        ]
        return runs[:limit]

    def runs(self, kind: RunKind | None = None, *, limit: int = 50) -> list[StoredRun]:
        records = [_stored_run_from_data(item) for item in self._run_items()]
        runs = [record for record in records if record is not None]
        if kind is not None:
            runs = [record for record in runs if record.kind == kind]
        runs.sort(key=lambda run: run.started_at, reverse=True)
        return runs if limit <= 0 else runs[:limit]

    def run(self, run_id: str) -> StoredRun | None:
        for item in self._run_items():
            if item.get("id") == run_id:
                return _stored_run_from_data(item)
        return None

    def delete_run(self, run_id: str) -> dict[str, object]:
        with self._lock:
            run = self.run(run_id)
            if run is None:
                raise KeyError(run_id)
            runs = [_stored_run_from_data(item) for item in self._run_items() if item.get("id") != run_id]
            retries = [item for item in self._retry_items() if item.get("run_id") != run_id]
            history_path = self._run_history_path(run_id, run)
            history_deleted = False
            if history_path.exists():
                history_path.unlink()
                history_deleted = True
            self._write_runs(runs)
            self._write_retries(retries)
            return {
                "id": run_id,
                "history_deleted": history_deleted,
                "history_path": relative_path(history_path, self.runtime.repo_root),
            }

    def retries(self, run_id: str) -> list[dict[str, object]]:
        rows = [item for item in self._retry_items() if item.get("run_id") == run_id]
        rows.sort(key=lambda item: _int_value(item.get("retry_index")))
        return [self._retry_with_history(row) for row in rows]

    def _upsert_run(self, patch: dict[str, object]) -> None:
        with self._lock:
            run_id = str(patch.get("id") or "")
            if not run_id:
                raise ValueError("run id is required")
            by_id = {str(item.get("id") or ""): item for item in self._run_items() if item.get("id")}
            data = dict(by_id.get(run_id) or {})
            data.update(patch)
            data.setdefault("started_at", _now())
            data.setdefault("updated_at", data["started_at"])
            data.setdefault("title", run_id)
            data.setdefault("kind", "manual")
            by_id[run_id] = data
            self._write_runs([_stored_run_from_data(item) for item in by_id.values()])

    def _run_items(self) -> list[dict[str, object]]:
        data = read_json_object(self.run_records_path)
        runs = data.get("runs")
        return [item for item in runs if isinstance(item, dict)] if isinstance(runs, list) else []

    def _retry_items(self) -> list[dict[str, object]]:
        data = read_json_object(self.retries_path)
        retries = data.get("retries")
        return [item for item in retries if isinstance(item, dict)] if isinstance(retries, list) else []

    def _write_retry_history(
        self,
        *,
        run_id: str,
        retry_id: str,
        retry_index: int,
        retry_group: int,
        status: str,
        started_at: str,
        updated_at: str,
        ended_at: str,
        return_code: int | None,
        task_ids: list[str],
        task_results: list[dict[str, Any]],
        log_entries: list[dict[str, Any]],
        log_files: dict[str, str] | None,
        generated_config_dir: str | None,
        maacore_log_file: str | None,
    ) -> str:
        run = self.run(run_id)
        path = self._run_history_path(run_id, run)
        existing = read_json_object(path)
        retries = [item for item in existing.get("retries", []) if isinstance(item, dict)]
        retries = [item for item in retries if item.get("id") != retry_id]
        retries.append(
            {
                "id": retry_id,
                "run_id": run_id,
                "retry_index": retry_index,
                "retry_group": retry_group,
                "status": status,
                "started_at": started_at,
                "updated_at": updated_at,
                "ended_at": ended_at,
                "return_code": return_code,
                "task_ids": task_ids,
                "task_results": task_results,
                "log_entries": log_entries,
                "log_files": log_files or {},
                "generated_config_dir": generated_config_dir,
                "maacore_log_file": maacore_log_file,
                "closed": True,
            }
        )
        retries.sort(key=lambda item: _int_value(item.get("retry_index")))
        data: dict[str, object] = {
            "description": "Durable run history with retry-scoped visible log blocks.",
            "updated_at": _now(),
            "run": run.to_dict() if run is not None else {"id": run_id},
            "retries": retries,
        }
        write_json_object(path, data)
        return relative_path(path, self.runtime.repo_root)

    def _sync_run_history(self, run_id: str) -> None:
        run = self.run(run_id)
        if run is None:
            return
        path = self._run_history_path(run_id, run)
        existing = read_json_object(path)
        if not existing:
            return
        existing["description"] = existing.get("description") or "Durable run history with retry-scoped visible log blocks."
        existing["updated_at"] = _now()
        existing["run"] = run.to_dict()
        write_json_object(path, existing)

    def _retry_with_history(self, row: dict[str, object]) -> dict[str, object]:
        output = dict(row)
        if "log_entries" in output:
            return output
        history_file = output.get("log_entries_file")
        if not isinstance(history_file, str) or not history_file:
            output["log_entries"] = []
            return output
        path = self.runtime.repo_root / history_file
        data = read_json_object(path)
        retry_id = output.get("id")
        for item in data.get("retries", []):
            if isinstance(item, dict) and item.get("id") == retry_id:
                output["log_entries"] = item.get("log_entries") if isinstance(item.get("log_entries"), list) else []
                if "task_results" not in output and isinstance(item.get("task_results"), list):
                    output["task_results"] = item["task_results"]
                return output
        output["log_entries"] = []
        return output

    def _run_history_path(self, run_id: str, run: StoredRun | None) -> Path:
        if run is None:
            return self.runtime.run_history_dir / "unknown" / f"{run_id}.json"
        if run.kind == "schedule":
            return self.runtime.run_history_dir / "schedules" / _safe_path_part(run.schedule_id or "unknown-schedule") / f"{run_id}.json"
        if run.kind == "tool":
            return self.runtime.run_history_dir / "tools" / _safe_path_part(run.tool_id or "unknown-tool") / f"{run_id}.json"
        if run.kind == "maintenance":
            return self.runtime.run_history_dir / "maintenance" / _safe_path_part(run.maintenance_kind or "unknown-maintenance") / f"{run_id}.json"
        return self.runtime.run_history_dir / "manual" / f"{run_id}.json"

    def _trigger_items(self) -> list[dict[str, object]]:
        data = read_json_object(self.triggers_path)
        triggers = data.get("triggered_entries")
        return [item for item in triggers if isinstance(item, dict)] if isinstance(triggers, list) else []

    def _write_runs(self, runs: list[StoredRun | None]) -> None:
        records = [run for run in runs if run is not None]
        records.sort(key=lambda run: run.started_at, reverse=True)
        data = {
            "description": "Recent WebUI, scheduled, maintenance, and tool run records. The WebUI derives recent runs from this file.",
            "updated_at": _now(),
            "runs": [run.to_dict() for run in records[: self.retention.max_run_records]],
        }
        write_json_object(self.run_records_path, data)

    def _write_retries(self, retries: list[dict[str, object]]) -> None:
        data = {
            "description": "Per-retry run index. Log blocks are stored in history/linux-maa/runs and referenced by log_entries_file.",
            "updated_at": _now(),
            "retries": retries,
        }
        write_json_object(self.retries_path, data)

    def _write_triggers(self, triggers: list[dict[str, object]]) -> None:
        data = {
            "description": "Schedule entries already triggered for a game day; used to avoid duplicate scheduled execution.",
            "updated_at": _now(),
            "triggered_entries": triggers,
        }
        write_json_object(self.triggers_path, data)

    def _daily_stats_data(self) -> dict[str, Any]:
        data = read_json_object(self.daily_stats_path)
        if "schedules" not in data:
            return {
                "description": "Per-schedule daily child-task run/success counters used by the scheduler policy.",
                "updated_at": _now(),
                "schedules": {},
            }
        return data

    def _write_daily_stats(self, data: dict[str, Any]) -> None:
        data.setdefault("description", "Per-schedule daily child-task run/success counters used by the scheduler policy.")
        write_json_object(self.daily_stats_path, data)

    def _prune_daily_stats(self) -> None:
        missing = not self.daily_stats_path.exists()
        data = self._daily_stats_data()
        schedules = _dict_value(data.get("schedules"))
        cutoff = datetime.now() - timedelta(days=max(0, self.retention.max_scheduler_state_days))
        cutoff_key = cutoff.date().isoformat()
        changed = missing
        for schedule in schedules.values():
            if not isinstance(schedule, dict):
                continue
            days = _dict_value(schedule.get("days"))
            for game_day in list(days):
                if str(game_day) < cutoff_key:
                    del days[game_day]
                    changed = True
        if changed:
            data["updated_at"] = _now()
            self._write_daily_stats(data)


def _stored_run_from_data(data: dict[str, object]) -> StoredRun | None:
    run_id = str(data.get("id") or "")
    kind = str(data.get("kind") or "manual")
    if not run_id or kind not in {"manual", "schedule", "maintenance", "tool"}:
        return None
    selected = data.get("selected_task_ids")
    summary = data.get("summary")
    log_files = data.get("log_files")
    return StoredRun(
        id=run_id,
        kind=kind,  # type: ignore[arg-type]
        status=str(data.get("status") or "unknown"),
        title=str(data.get("title") or run_id),
        started_at=str(data.get("started_at") or ""),
        updated_at=_optional_str(data.get("updated_at")),
        ended_at=_optional_str(data.get("ended_at")),
        return_code=_optional_int(data.get("return_code")),
        max_retries=max(1, _int_value(data.get("max_retries")) or 1),
        retry_count=_int_value(data.get("retry_count")),
        retry_group_count=_int_value(data.get("retry_group_count")),
        log_files={str(key): str(value) for key, value in log_files.items()} if isinstance(log_files, dict) else {},
        event_log_file=_optional_str(data.get("event_log_file")),
        maacore_log_file=_optional_str(data.get("maacore_log_file")),
        generated_config_dir=_optional_str(data.get("generated_config_dir")),
        selected_task_ids=[str(item) for item in selected] if isinstance(selected, list) else [],
        summary=dict(summary) if isinstance(summary, dict) else {},
        schedule_id=str(data.get("schedule_id") or ""),
        schedule_name=str(data.get("schedule_name") or ""),
        entry_id=str(data.get("entry_id") or ""),
        entry_name=str(data.get("entry_name") or ""),
        task_config=str(data.get("task_config") or ""),
        game_day=str(data.get("game_day") or ""),
        trigger=str(data.get("trigger") or ""),
        task=str(data.get("task") or ""),
        profile=str(data.get("profile") or ""),
        maintenance_kind=str(data.get("maintenance_kind") or ""),
        tool_id=str(data.get("tool_id") or ""),
        tool_title=str(data.get("tool_title") or ""),
    )


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _now() -> str:
    return server_now_iso()


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_path_part(value: str) -> str:
    return slugify(value) or "unknown"
