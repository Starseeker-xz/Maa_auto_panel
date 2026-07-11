from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.scheduler.models import DailyTaskStats
from maa_auto_panel.storage.files import read_json_object, write_json_object
from maa_auto_panel.time_utils import server_now_iso


@dataclass(frozen=True)
class SchedulerStateRetentionPolicy:
    max_trigger_records: int = 2000
    max_scheduler_state_days: int = 90


class SchedulerStateStore:
    """Scheduler-owned durable state outside generic run history."""

    def __init__(self, runtime: MaaRuntime, retention: SchedulerStateRetentionPolicy | None = None) -> None:
        self.runtime = runtime
        self.retention = retention or SchedulerStateRetentionPolicy()
        self._lock = threading.RLock()
        self.ensure_dirs()

    @property
    def triggers_path(self) -> Path:
        return self.runtime.scheduler_state_dir / "triggered-schedule-entries.json"

    @property
    def daily_stats_path(self) -> Path:
        return self.runtime.scheduler_state_dir / "daily-task-stats.json"

    def ensure_dirs(self) -> None:
        self.runtime.scheduler_state_dir.mkdir(parents=True, exist_ok=True)

    def enforce_retention(self) -> None:
        with self._lock:
            triggers = self._trigger_items()[-self.retention.max_trigger_records :]
            self._write_triggers(triggers)
            self._prune_daily_stats()

    def daily_stats(self, schedule_id: str, game_day: str) -> dict[str, DailyTaskStats]:
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

    def _trigger_items(self) -> list[dict[str, object]]:
        data = read_json_object(self.triggers_path)
        triggers = data.get("triggered_entries")
        return [item for item in triggers if isinstance(item, dict)] if isinstance(triggers, list) else []

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


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _now() -> str:
    return server_now_iso()
