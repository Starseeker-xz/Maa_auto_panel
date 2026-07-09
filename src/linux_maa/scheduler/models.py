from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from linux_maa.run_manager.state import RunTimeouts
from linux_maa.utils import slugify

RestartMode = Literal["none", "before_run", "before_retry"]


@dataclass(frozen=True)
class ScheduleEntry:
    """A single timed entry in a schedule: wall-clock time and enabled task ids."""
    id: str
    name: str
    time: str
    enabled: bool = True
    task_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScheduleRetryPolicy:
    """Retry behaviour for scheduled runs."""
    max_retries: int = 5
    buffer_every_retries: int = 0
    buffer_seconds: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScheduleTimeouts:
    """Generic timeout thresholds for scheduled attempts."""
    no_output_warning_seconds: int = 900
    no_output_kill_seconds: int = 1800
    runtime_warning_seconds: int = 1800
    runtime_kill_seconds: int = 3600
    stop_warning_seconds: int = 60
    stop_kill_seconds: int = 300

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_run_timeouts(self) -> RunTimeouts:
        return RunTimeouts(**self.to_dict())


@dataclass(frozen=True)
class RestartScriptPolicy:
    """Policy for when restart script executes and its variables."""
    mode: RestartMode = "none"
    script: str = ""
    variables: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScheduleConfig:
    """Top-level schedule config: entries, retry, timeouts, restart policy, profile, task config."""
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
    """Per-task execution policy: importance, unlimited runs, min daily successes, retry-even-on-success."""
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
    """Rolling daily counters for a task: total runs and successful runs within current game day."""
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
    return slugify(value)
