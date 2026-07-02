from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from linux_maa.maa.runtime import MaaRuntime
from linux_maa.storage.files import read_json_object, write_json_object


RunKind = Literal["manual", "schedule", "maintenance"]


@dataclass(frozen=True)
class StateRetentionPolicy:
    max_run_records: int = 500
    max_attempt_records: int = 2000
    max_trigger_records: int = 2000
    max_scheduler_state_days: int = 90


@dataclass(frozen=True)
class StoredRun:
    id: str
    kind: RunKind
    status: str
    title: str
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None
    return_code: int | None = None
    attempt_count: int = 0
    retry_group_count: int = 0
    log_file: str | None = None
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

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "title": self.title,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "return_code": self.return_code,
            "attempt_count": self.attempt_count,
            "retry_group_count": self.retry_group_count,
            "log_file": self.log_file,
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
    def run_records_path(self):
        return self.runtime.run_state_dir / "recent-run-records.json"

    @property
    def attempts_path(self):
        return self.runtime.run_state_dir / "scheduled-run-attempts.json"

    @property
    def triggers_path(self):
        return self.runtime.scheduler_state_dir / "triggered-schedule-entries.json"

    @property
    def daily_stats_path(self):
        return self.runtime.scheduler_state_dir / "daily-task-stats.json"

    def ensure_dirs(self) -> None:
        self.runtime.run_state_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.scheduler_state_dir.mkdir(parents=True, exist_ok=True)

    def enforce_retention(self) -> None:
        with self._lock:
            self._write_runs(self.runs(limit=0))
            attempts = self._attempt_items()[-self.retention.max_attempt_records :]
            self._write_attempts(attempts)
            triggers = self._trigger_items()[-self.retention.max_trigger_records :]
            self._write_triggers(triggers)
            self._prune_daily_stats()

    def create_manual_run(
        self,
        *,
        run_id: str,
        task: str,
        profile: str,
        log_file: str | None = None,
        log_files: dict[str, str] | None = None,
        event_log_file: str | None = None,
    ) -> None:
        self._upsert_run(
            {
                "id": run_id,
                "kind": "manual",
                "status": "running",
                "title": task,
                "created_at": _now(),
                "started_at": _now(),
                "task": task,
                "profile": profile,
                "log_file": log_file,
                "log_files": log_files or {},
                "event_log_file": event_log_file,
            }
        )

    def create_maintenance_run(
        self,
        *,
        run_id: str,
        kind: str,
        title: str,
        log_file: str | None = None,
        log_files: dict[str, str] | None = None,
        event_log_file: str | None = None,
    ) -> None:
        self._upsert_run(
            {
                "id": run_id,
                "kind": "maintenance",
                "status": "running",
                "title": title,
                "created_at": _now(),
                "started_at": _now(),
                "maintenance_kind": kind,
                "log_file": log_file,
                "log_files": log_files or {},
                "event_log_file": event_log_file,
            }
        )

    def finish_generic_run(
        self,
        run_id: str,
        *,
        status: str,
        return_code: int | None = None,
        summary: dict[str, Any] | None = None,
        maacore_log_file: str | None = None,
    ) -> None:
        patch: dict[str, object] = {
            "id": run_id,
            "status": status,
            "ended_at": _now(),
            "return_code": return_code,
        }
        if summary is not None:
            patch["summary"] = summary
        if maacore_log_file is not None:
            patch["maacore_log_file"] = maacore_log_file
        self._upsert_run(patch)

    def create_run(
        self,
        *,
        run_id: str,
        schedule_id: str,
        schedule_name: str,
        entry_id: str,
        entry_name: str,
        task_config: str,
        game_day: str,
        trigger: str,
        selected_task_ids: list[str],
        log_file: str | None = None,
        log_files: dict[str, str] | None = None,
        event_log_file: str | None = None,
    ) -> None:
        self._upsert_run(
            {
                "id": run_id,
                "kind": "schedule",
                "status": "running",
                "title": f"{schedule_name} / {entry_name}",
                "created_at": _now(),
                "started_at": _now(),
                "schedule_id": schedule_id,
                "schedule_name": schedule_name,
                "entry_id": entry_id,
                "entry_name": entry_name,
                "task_config": task_config,
                "game_day": game_day,
                "trigger": trigger,
                "selected_task_ids": selected_task_ids,
                "log_file": log_file,
                "log_files": log_files or {},
                "event_log_file": event_log_file,
            }
        )

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        attempt_count: int,
        retry_group_count: int,
        log_file: str | None,
        summary: dict[str, Any],
        maacore_log_file: str | None = None,
        log_files: dict[str, str] | None = None,
    ) -> None:
        patch: dict[str, object] = {
            "id": run_id,
            "status": status,
            "ended_at": _now(),
            "attempt_count": attempt_count,
            "retry_group_count": retry_group_count,
            "log_file": log_file,
            "summary": summary,
        }
        if log_files is not None:
            patch["log_files"] = log_files
        if maacore_log_file is not None:
            patch["maacore_log_file"] = maacore_log_file
        self._upsert_run(patch)

    def add_attempt(
        self,
        *,
        attempt_id: str,
        run_id: str,
        attempt_index: int,
        retry_group: int,
        status: str,
        started_at: str,
        ended_at: str,
        return_code: int | None,
        task_ids: list[str],
        task_results: list[dict[str, Any]],
        log_entries: list[dict[str, Any]],
        log_file: str | None = None,
        log_files: dict[str, str] | None = None,
        generated_config_dir: str | None = None,
    ) -> None:
        with self._lock:
            attempts = [item for item in self._attempt_items() if item.get("id") != attempt_id]
            attempts.append(
                {
                    "id": attempt_id,
                    "run_id": run_id,
                    "attempt_index": attempt_index,
                    "retry_group": retry_group,
                    "status": status,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "return_code": return_code,
                    "task_ids": task_ids,
                    "task_results": task_results,
                    "log_entries": log_entries,
                    "log_file": log_file,
                    "log_files": log_files or {},
                    "generated_config_dir": generated_config_dir,
                }
            )
            self._write_attempts(attempts[-self.retention.max_attempt_records :])

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
            if (
                item.get("schedule_id") == schedule_id
                and item.get("entry_id") == entry_id
                and item.get("game_day") == game_day
            ):
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
        runs.sort(key=lambda run: run.created_at, reverse=True)
        return runs if limit <= 0 else runs[:limit]

    def run(self, run_id: str) -> StoredRun | None:
        for item in self._run_items():
            if item.get("id") == run_id:
                return _stored_run_from_data(item)
        return None

    def attempts(self, run_id: str) -> list[dict[str, object]]:
        rows = [item for item in self._attempt_items() if item.get("run_id") == run_id]
        rows.sort(key=lambda item: _int_value(item.get("attempt_index")))
        return rows

    def _upsert_run(self, patch: dict[str, object]) -> None:
        with self._lock:
            run_id = str(patch.get("id") or "")
            if not run_id:
                raise ValueError("run id is required")
            by_id = {str(item.get("id") or ""): item for item in self._run_items() if item.get("id")}
            data = dict(by_id.get(run_id) or {})
            data.update(patch)
            if "created_at" not in data:
                data["created_at"] = _now()
            if "title" not in data:
                data["title"] = run_id
            if "kind" not in data:
                data["kind"] = "manual"
            by_id[run_id] = data
            self._write_runs([_stored_run_from_data(item) for item in by_id.values()])

    def _run_items(self) -> list[dict[str, object]]:
        data = read_json_object(self.run_records_path)
        runs = data.get("runs")
        return [item for item in runs if isinstance(item, dict)] if isinstance(runs, list) else []

    def _attempt_items(self) -> list[dict[str, object]]:
        data = read_json_object(self.attempts_path)
        attempts = data.get("attempts")
        return [item for item in attempts if isinstance(item, dict)] if isinstance(attempts, list) else []

    def _trigger_items(self) -> list[dict[str, object]]:
        data = read_json_object(self.triggers_path)
        triggers = data.get("triggered_entries")
        return [item for item in triggers if isinstance(item, dict)] if isinstance(triggers, list) else []

    def _write_runs(self, runs: list[StoredRun | None]) -> None:
        records = [run for run in runs if run is not None]
        records.sort(key=lambda run: run.created_at, reverse=True)
        data = {
            "description": "Recent WebUI, scheduled, and maintenance run records. The WebUI derives recent runs from this file.",
            "updated_at": _now(),
            "runs": [run.to_dict() for run in records[: self.retention.max_run_records]],
        }
        write_json_object(self.run_records_path, data)

    def _write_attempts(self, attempts: list[dict[str, object]]) -> None:
        data = {
            "description": "Per-attempt records for scheduled runs. Manual and maintenance runs do not use retry attempts.",
            "updated_at": _now(),
            "attempts": attempts,
        }
        write_json_object(self.attempts_path, data)

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
    if not run_id or kind not in {"manual", "schedule", "maintenance"}:
        return None
    selected = data.get("selected_task_ids")
    summary = data.get("summary")
    log_files = data.get("log_files")
    return StoredRun(
        id=run_id,
        kind=kind,  # type: ignore[arg-type]
        status=str(data.get("status") or "unknown"),
        title=str(data.get("title") or run_id),
        created_at=str(data.get("created_at") or ""),
        started_at=_optional_str(data.get("started_at")),
        ended_at=_optional_str(data.get("ended_at")),
        return_code=_optional_int(data.get("return_code")),
        attempt_count=_int_value(data.get("attempt_count")),
        retry_group_count=_int_value(data.get("retry_group_count")),
        log_file=_optional_str(data.get("log_file")),
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
    )


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


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
