from __future__ import annotations

import re
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


RestartMode = Literal["none", "before_run", "before_retry_group", "before_retry"]


@dataclass(frozen=True)
class ScheduleEntry:
    id: str
    name: str
    time: str
    enabled: bool = True
    task_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScheduleRetryPolicy:
    max_attempts_per_group: int = 5
    group_buffer_seconds: int = 300
    max_groups: int = 3

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScheduleTimeouts:
    child_warning_seconds: int = 900
    child_danger_seconds: int = 1200
    child_kill_seconds: int = 1800
    run_warning_seconds: int = 1800
    run_danger_seconds: int = 2400
    run_kill_seconds: int = 3600

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RestartScriptPolicy:
    mode: RestartMode = "none"
    script: str = ""
    variables: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScheduleConfig:
    id: str
    name: str
    enabled: bool
    task_config: str
    profile_name: str
    profile_data: dict[str, Any]
    log_level: int = 1
    entries: list[ScheduleEntry] = field(default_factory=list)
    retry: ScheduleRetryPolicy = field(default_factory=ScheduleRetryPolicy)
    timeouts: ScheduleTimeouts = field(default_factory=ScheduleTimeouts)
    restart: RestartScriptPolicy = field(default_factory=RestartScriptPolicy)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "task_config": self.task_config,
            "profile_name": self.profile_name,
            "profile": deepcopy(self.profile_data),
            "log_level": self.log_level,
            "entries": [entry.to_dict() for entry in self.entries],
            "retry": self.retry.to_dict(),
            "timeouts": self.timeouts.to_dict(),
            "restart": self.restart.to_dict(),
        }


@dataclass(frozen=True)
class TaskPolicy:
    id: str
    name: str
    type: str
    important: bool = True
    unlimited_runs: bool = True
    min_daily_successes: int = 1
    retry_even_success: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DailyTaskStats:
    task_id: str
    task_name: str
    successes: int = 0
    runs: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def schedule_id_from_name(name: str) -> str:
    return slug(name) or f"schedule-{uuid.uuid4().hex[:8]}"


def entry_id_from_time(time_text: str) -> str:
    return f"t{time_text.replace(':', '')}"


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-").lower()[:64]
