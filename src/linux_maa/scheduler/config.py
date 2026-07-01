from __future__ import annotations

import tomllib
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomli_w

from linux_maa.config.manager import ConfigFile, ConfigManager
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.scheduler.models import (
    RestartScriptPolicy,
    ScheduleConfig,
    ScheduleEntry,
    ScheduleRetryPolicy,
    ScheduleTimeouts,
    entry_id_from_time,
    schedule_id_from_name,
    slug,
)
from linux_maa.storage import TrashManager, TrashRecord
from linux_maa.utils import bounded_int, relative_path, validate_file_name, write_text_atomic


@dataclass(frozen=True)
class ScheduleConfigFile:
    id: str
    name: str
    filename: str
    path: str
    size: int
    modified_at: float

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "filename": self.filename,
            "path": self.path,
            "size": self.size,
            "modified_at": self.modified_at,
        }


class ScheduleConfigManager:
    def __init__(self, runtime: MaaRuntime, configs: ConfigManager) -> None:
        self.runtime = runtime
        self.configs = configs
        self.trash = TrashManager(runtime.framework_config_dir / ".trash", repo_root=runtime.repo_root)

    def ensure_dirs(self) -> None:
        self.runtime.schedule_config_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.script_dir.mkdir(parents=True, exist_ok=True)

    def list_files(self) -> list[ScheduleConfigFile]:
        self.ensure_dirs()
        files: list[ScheduleConfigFile] = []
        for path in sorted(self.runtime.schedule_config_dir.glob("*.toml"), key=lambda item: item.name):
            try:
                config = self.read(path.stem)
                config_id = config.id
                name = config.name
            except Exception:
                config_id = path.stem
                name = path.stem
            stat = path.stat()
            files.append(
                ScheduleConfigFile(
                    id=config_id,
                    name=name,
                    filename=path.name,
                    path=relative_path(path, self.runtime.repo_root),
                    size=stat.st_size,
                    modified_at=stat.st_mtime,
                )
            )
        return files

    def read(self, schedule_id: str) -> ScheduleConfig:
        path = self.resolve(schedule_id)
        return schedule_from_data(tomllib.loads(path.read_text(encoding="utf-8")), fallback_id=path.stem)

    def write(self, schedule_id: str, payload: dict[str, Any]) -> ScheduleConfig:
        config = schedule_from_data(payload, fallback_id=schedule_id)
        path = self.resolve_for_write(config.id)
        write_text_atomic(path, tomli_w.dumps(schedule_to_toml_data(config)))
        return self.read(config.id)

    def create_default(self, name: str, task_config: str, default_profile: dict[str, Any], task_ids: list[str]) -> ScheduleConfig:
        schedule_id = unique_schedule_id(self.runtime.schedule_config_dir, schedule_id_from_name(name))
        config = ScheduleConfig(
            id=schedule_id,
            name=name.strip() or schedule_id,
            enabled=False,
            task_config=task_config,
            profile_name=f"{schedule_id}-profile",
            profile_data=deepcopy(default_profile),
            entries=[
                ScheduleEntry(id="t0400", name="04:00", time="04:00", enabled=True, task_ids=list(task_ids)),
                ScheduleEntry(id="t0800", name="08:00", time="08:00", enabled=True, task_ids=list(task_ids)),
                ScheduleEntry(id="t1600", name="16:00", time="16:00", enabled=True, task_ids=list(task_ids)),
                ScheduleEntry(id="t2200", name="22:00", time="22:00", enabled=True, task_ids=list(task_ids)),
            ],
        )
        path = self.resolve_for_write(config.id)
        write_text_atomic(path, tomli_w.dumps(schedule_to_toml_data(config)))
        return self.read(config.id)

    def delete(self, schedule_id: str) -> TrashRecord:
        path = self.resolve(schedule_id)
        return self.trash.move(path, label=f"schedule:{path.name}")

    def resolve(self, schedule_id: str) -> Path:
        requested = validate_file_name(schedule_id, label="schedule id")
        candidates = [self.runtime.schedule_config_dir / requested.name] if requested.suffix else [self.runtime.schedule_config_dir / f"{schedule_id}.toml"]
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() == ".toml":
                return candidate
        raise FileNotFoundError(schedule_id)

    def resolve_for_write(self, schedule_id: str) -> Path:
        normalized = slug(schedule_id)
        if not normalized:
            raise ValueError("Invalid schedule id")
        return self.runtime.schedule_config_dir / f"{normalized}.toml"

    def file_info(self, config: ScheduleConfig) -> ConfigFile:
        path = self.resolve(config.id)
        stat = path.stat()
        return ConfigFile(
            kind="schedules",
            name=config.id,
            filename=path.name,
            path=relative_path(path, self.runtime.repo_root),
            suffix="toml",
            size=stat.st_size,
            modified_at=stat.st_mtime,
        )


def schedule_from_data(data: dict[str, Any], *, fallback_id: str) -> ScheduleConfig:
    schedule_id = slug(str(data.get("id") or fallback_id))
    if not schedule_id:
        raise ValueError("Schedule id cannot be empty")

    raw_entries = data.get("entries") if isinstance(data.get("entries"), list) else []
    entries = [entry_from_data(item, index=index) for index, item in enumerate(raw_entries, start=1) if isinstance(item, dict)]
    if not entries:
        entries = [ScheduleEntry(id="t0400", name="04:00", time="04:00", enabled=True, task_ids=[])]

    raw_profile = data.get("profile")
    profile_data = deepcopy(raw_profile) if isinstance(raw_profile, dict) else {}
    raw_retry = data.get("retry") if isinstance(data.get("retry"), dict) else {}
    raw_timeouts = data.get("timeouts") if isinstance(data.get("timeouts"), dict) else {}
    raw_restart = data.get("restart") if isinstance(data.get("restart"), dict) else {}

    return ScheduleConfig(
        id=schedule_id,
        name=str(data.get("name") or schedule_id),
        enabled=bool(data.get("enabled", False)),
        task_config=str(data.get("task_config") or ""),
        profile_name=slug(str(data.get("profile_name") or f"{schedule_id}-profile")) or f"{schedule_id}-profile",
        profile_data=profile_data,
            log_level=bounded_int(data.get("log_level"), default=1, minimum=0, maximum=3),
        entries=entries,
        retry=ScheduleRetryPolicy(
            max_attempts_per_group=bounded_int(raw_retry.get("max_attempts_per_group"), default=5, minimum=1, maximum=50),
            group_buffer_seconds=bounded_int(raw_retry.get("group_buffer_seconds"), default=300, minimum=0, maximum=86400),
            max_groups=bounded_int(raw_retry.get("max_groups"), default=3, minimum=1, maximum=50),
        ),
        timeouts=ScheduleTimeouts(
            child_warning_seconds=bounded_int(raw_timeouts.get("child_warning_seconds"), default=900, minimum=0, maximum=86400),
            child_danger_seconds=bounded_int(raw_timeouts.get("child_danger_seconds"), default=1200, minimum=0, maximum=86400),
            child_kill_seconds=bounded_int(raw_timeouts.get("child_kill_seconds"), default=1800, minimum=0, maximum=86400),
            run_warning_seconds=bounded_int(raw_timeouts.get("run_warning_seconds"), default=1800, minimum=0, maximum=172800),
            run_danger_seconds=bounded_int(raw_timeouts.get("run_danger_seconds"), default=2400, minimum=0, maximum=172800),
            run_kill_seconds=bounded_int(raw_timeouts.get("run_kill_seconds"), default=3600, minimum=0, maximum=172800),
        ),
        restart=RestartScriptPolicy(
            mode=_restart_mode(raw_restart.get("mode")),
            script=str(raw_restart.get("script") or ""),
            variables={str(key): str(value) for key, value in (raw_restart.get("variables") or {}).items()} if isinstance(raw_restart.get("variables"), dict) else {},
        ),
    )


def entry_from_data(data: dict[str, Any], *, index: int) -> ScheduleEntry:
    time_text = normalize_time(str(data.get("time") or "04:00"))
    task_ids = [slug(str(item)) for item in data.get("task_ids", []) if str(item).strip()] if isinstance(data.get("task_ids"), list) else []
    return ScheduleEntry(
        id=slug(str(data.get("id") or entry_id_from_time(time_text))) or f"entry-{index}",
        name=str(data.get("name") or time_text),
        time=time_text,
        enabled=bool(data.get("enabled", True)),
        task_ids=task_ids,
    )


def schedule_to_toml_data(config: ScheduleConfig) -> dict[str, Any]:
    return {
        "id": config.id,
        "name": config.name,
        "enabled": config.enabled,
        "task_config": config.task_config,
        "profile_name": config.profile_name,
        "log_level": config.log_level,
        "profile": deepcopy(config.profile_data),
        "retry": config.retry.to_dict(),
        "timeouts": config.timeouts.to_dict(),
        "restart": config.restart.to_dict(),
        "entries": [entry.to_dict() for entry in config.entries],
    }


def normalize_time(value: str) -> str:
    parts = value.strip().split(":")
    if len(parts) < 2:
        raise ValueError(f"Invalid time: {value}")
    hour = int(parts[0])
    minute = int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Invalid time: {value}")
    return f"{hour:02d}:{minute:02d}"


def unique_schedule_id(directory: Path, base: str) -> str:
    candidate = slug(base) or "schedule"
    if not (directory / f"{candidate}.toml").exists():
        return candidate
    suffix = 2
    while (directory / f"{candidate}-{suffix}.toml").exists():
        suffix += 1
    return f"{candidate}-{suffix}"


def _restart_mode(value: object) -> str:
    text = str(value or "none")
    return text if text in {"none", "before_run", "before_retry_group", "before_retry"} else "none"
