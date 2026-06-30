from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from linux_maa.scheduler.models import DailyTaskStats


@dataclass(frozen=True)
class StoredRun:
    id: str
    schedule_id: str
    schedule_name: str
    entry_id: str
    entry_name: str
    task_config: str
    game_day: str
    trigger: str
    status: str
    created_at: str
    started_at: str | None
    ended_at: str | None
    attempt_count: int
    retry_group_count: int
    log_file: str | None
    selected_task_ids: list[str]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "schedule_id": self.schedule_id,
            "schedule_name": self.schedule_name,
            "entry_id": self.entry_id,
            "entry_name": self.entry_name,
            "task_config": self.task_config,
            "game_day": self.game_day,
            "trigger": self.trigger,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "attempt_count": self.attempt_count,
            "retry_group_count": self.retry_group_count,
            "log_file": self.log_file,
            "selected_task_ids": list(self.selected_task_ids),
            "summary": dict(self.summary),
        }


class ScheduleStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                create table if not exists scheduled_runs (
                  id text primary key,
                  schedule_id text not null,
                  schedule_name text not null,
                  entry_id text not null,
                  entry_name text not null,
                  task_config text not null,
                  game_day text not null,
                  trigger text not null,
                  status text not null,
                  created_at text not null,
                  started_at text,
                  ended_at text,
                  attempt_count integer not null default 0,
                  retry_group_count integer not null default 0,
                  log_file text,
                  selected_task_ids text not null default '[]',
                  summary text not null default '{}'
                );
                create table if not exists scheduled_attempts (
                  id text primary key,
                  run_id text not null,
                  attempt_index integer not null,
                  retry_group integer not null,
                  status text not null,
                  started_at text not null,
                  ended_at text,
                  return_code integer,
                  task_ids text not null,
                  task_results text not null default '[]',
                  log_entries text not null default '[]'
                );
                create table if not exists daily_task_stats (
                  schedule_id text not null,
                  game_day text not null,
                  task_id text not null,
                  task_name text not null,
                  successes integer not null default 0,
                  runs integer not null default 0,
                  updated_at text not null,
                  primary key (schedule_id, game_day, task_id)
                );
                create table if not exists scheduled_triggers (
                  schedule_id text not null,
                  entry_id text not null,
                  game_day text not null,
                  run_id text not null,
                  ran_at text not null,
                  primary key (schedule_id, entry_id, game_day)
                );
                """
            )

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
    ) -> None:
        now = _now()
        with self._connect() as db:
            db.execute(
                """
                insert into scheduled_runs (
                  id, schedule_id, schedule_name, entry_id, entry_name, task_config,
                  game_day, trigger, status, created_at, started_at, selected_task_ids
                ) values (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)
                """,
                (
                    run_id,
                    schedule_id,
                    schedule_name,
                    entry_id,
                    entry_name,
                    task_config,
                    game_day,
                    trigger,
                    now,
                    now,
                    json.dumps(selected_task_ids, ensure_ascii=False),
                ),
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
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                update scheduled_runs
                set status = ?, ended_at = ?, attempt_count = ?, retry_group_count = ?, log_file = ?, summary = ?
                where id = ?
                """,
                (status, _now(), attempt_count, retry_group_count, log_file, json.dumps(summary, ensure_ascii=False), run_id),
            )

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
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                insert into scheduled_attempts (
                  id, run_id, attempt_index, retry_group, status, started_at, ended_at,
                  return_code, task_ids, task_results, log_entries
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    run_id,
                    attempt_index,
                    retry_group,
                    status,
                    started_at,
                    ended_at,
                    return_code,
                    json.dumps(task_ids, ensure_ascii=False),
                    json.dumps(task_results, ensure_ascii=False),
                    json.dumps(log_entries, ensure_ascii=False),
                ),
            )

    def daily_stats(self, schedule_id: str, game_day: str) -> dict[str, DailyTaskStats]:
        with self._connect() as db:
            rows = db.execute(
                """
                select task_id, task_name, successes, runs
                from daily_task_stats
                where schedule_id = ? and game_day = ?
                """,
                (schedule_id, game_day),
            ).fetchall()
        return {
            row["task_id"]: DailyTaskStats(
                task_id=row["task_id"],
                task_name=row["task_name"],
                successes=row["successes"],
                runs=row["runs"],
            )
            for row in rows
        }

    def update_daily_stats(
        self,
        *,
        schedule_id: str,
        game_day: str,
        task_names: dict[str, str],
        task_statuses: dict[str, str],
    ) -> None:
        now = _now()
        with self._connect() as db:
            for task_id, task_name in task_names.items():
                succeeded = 1 if task_statuses.get(task_id) == "succeeded" else 0
                db.execute(
                    """
                    insert into daily_task_stats (schedule_id, game_day, task_id, task_name, successes, runs, updated_at)
                    values (?, ?, ?, ?, ?, 1, ?)
                    on conflict(schedule_id, game_day, task_id) do update set
                      task_name = excluded.task_name,
                      successes = daily_task_stats.successes + excluded.successes,
                      runs = daily_task_stats.runs + 1,
                      updated_at = excluded.updated_at
                    """,
                    (schedule_id, game_day, task_id, task_name, succeeded, now),
                )

    def mark_triggered(self, *, schedule_id: str, entry_id: str, game_day: str, run_id: str) -> None:
        with self._connect() as db:
            db.execute(
                """
                insert or ignore into scheduled_triggers (schedule_id, entry_id, game_day, run_id, ran_at)
                values (?, ?, ?, ?, ?)
                """,
                (schedule_id, entry_id, game_day, run_id, _now()),
            )

    def already_triggered(self, *, schedule_id: str, entry_id: str, game_day: str) -> bool:
        with self._connect() as db:
            row = db.execute(
                """
                select 1 from scheduled_triggers
                where schedule_id = ? and entry_id = ? and game_day = ?
                """,
                (schedule_id, entry_id, game_day),
            ).fetchone()
        return row is not None

    def recent_runs(self, schedule_id: str | None = None, *, limit: int = 20) -> list[StoredRun]:
        where = "where schedule_id = ?" if schedule_id else ""
        params: tuple[object, ...] = (schedule_id, limit) if schedule_id else (limit,)
        with self._connect() as db:
            rows = db.execute(
                f"""
                select * from scheduled_runs
                {where}
                order by created_at desc
                limit ?
                """,
                params,
            ).fetchall()
        return [_stored_run_from_row(row) for row in rows]

    def attempts(self, run_id: str) -> list[dict[str, object]]:
        with self._connect() as db:
            rows = db.execute(
                """
                select * from scheduled_attempts
                where run_id = ?
                order by attempt_index asc
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "run_id": row["run_id"],
                "attempt_index": row["attempt_index"],
                "retry_group": row["retry_group"],
                "status": row["status"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "return_code": row["return_code"],
                "task_ids": _loads(row["task_ids"], []),
                "task_results": _loads(row["task_results"], []),
                "log_entries": _loads(row["log_entries"], []),
            }
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db


def _stored_run_from_row(row: sqlite3.Row) -> StoredRun:
    return StoredRun(
        id=row["id"],
        schedule_id=row["schedule_id"],
        schedule_name=row["schedule_name"],
        entry_id=row["entry_id"],
        entry_name=row["entry_name"],
        task_config=row["task_config"],
        game_day=row["game_day"],
        trigger=row["trigger"],
        status=row["status"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        attempt_count=row["attempt_count"],
        retry_group_count=row["retry_group_count"],
        log_file=row["log_file"],
        selected_task_ids=_loads(row["selected_task_ids"], []),
        summary=_loads(row["summary"], {}),
    )


def _loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
