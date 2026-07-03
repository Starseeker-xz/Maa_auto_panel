from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import tomllib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import tomli_w

from linux_maa.maa.runtime import MaaRuntime
from linux_maa.utils import relative_path, write_text_atomic


DEFAULT_FRAMEWORK_SETTINGS: dict[str, Any] = {
    "$schema": "./settings.schema.json",
    "framework": {
        "timezone": {
            "mode": "auto",
            "manual_timezone": "UTC",
            "client_timezone": "",
        },
        "scheduler": {
            "enabled": False,
        },
    },
    "theme": {
        "mode": "system",
        "color": "cyan",
    },
}


@dataclass(frozen=True)
class TimezoneInfo:
    """Immutable parsed timezone info from framework settings."""
    name: str
    offset_minutes: int
    label: str
    resolved_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "offset_minutes": self.offset_minutes,
            "label": self.label,
            "resolved_at": self.resolved_at,
        }


class FrameworkSettingsManager:
    """Manages framework-level settings.toml with timezone resolution and defaults."""
    def __init__(self, runtime: MaaRuntime) -> None:
        self.runtime = runtime

    @property
    def path(self) -> Path:
        return self.runtime.framework_config_dir / "settings.toml"

    def read(self) -> dict[str, object]:
        data = self._load()
        return {
            "file": {
                "path": relative_path(self.path, self.runtime.repo_root),
                "exists": self.path.exists(),
            },
            "data": data,
            "effective_timezone": self.resolve_timezone(data).to_dict(),
        }

    def write(self, data: dict[str, Any]) -> dict[str, object]:
        merged = self._merge_defaults(data)
        resolved = self.resolve_timezone(merged)
        timezone_settings = merged.setdefault("framework", {}).setdefault("timezone", {})
        if isinstance(timezone_settings, dict):
            timezone_settings["auto_resolved_name"] = resolved.name
            timezone_settings["auto_resolved_offset_minutes"] = resolved.offset_minutes
            timezone_settings["auto_resolved_at"] = resolved.resolved_at

        write_text_atomic(self.path, tomli_w.dumps(merged))
        return self.read()

    def resolve_timezone(self, data: dict[str, Any]) -> TimezoneInfo:
        settings = data.get("framework", {}).get("timezone", {}) if isinstance(data.get("framework"), dict) else {}
        mode = settings.get("mode") if isinstance(settings, dict) else "auto"
        if mode == "client":
            client = str(settings.get("client_timezone") or "") if isinstance(settings, dict) else ""
            if client.strip():
                return _manual_timezone_info(client)
        if mode == "manual":
            manual = str(settings.get("manual_timezone") or "UTC") if isinstance(settings, dict) else "UTC"
            return _manual_timezone_info(manual)
        return _local_timezone_info()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._merge_defaults({})
        loaded = tomllib.loads(self.path.read_text(encoding="utf-8"))
        return self._merge_defaults(loaded)

    def _merge_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(DEFAULT_FRAMEWORK_SETTINGS)
        _deep_update(merged, data)
        framework = merged.get("framework")
        timezone_settings = framework.get("timezone") if isinstance(framework, dict) else None
        if isinstance(timezone_settings, dict):
            timezone_settings.pop("game_day_offset_hours", None)
        return merged


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _local_timezone_info() -> TimezoneInfo:
    now = datetime.now().astimezone()
    offset = now.utcoffset() or timedelta(0)
    offset_minutes = int(offset.total_seconds() // 60)
    name = str(now.tzinfo) if now.tzinfo else "UTC"
    return TimezoneInfo(name=name, offset_minutes=offset_minutes, label=_offset_label(offset_minutes), resolved_at=now.isoformat(timespec="seconds"))


def _manual_timezone_info(value: str) -> TimezoneInfo:
    raw_value = value.strip()
    parsed = raw_value.upper()
    if not raw_value:
        raise ValueError("Timezone cannot be empty")

    if parsed in {"UTC", "Z"}:
        offset_minutes = 0
        tz = timezone.utc
        now = datetime.now(tz)
        return TimezoneInfo(name="UTC", offset_minutes=offset_minutes, label=_offset_label(offset_minutes), resolved_at=now.isoformat(timespec="seconds"))

    try:
        tz = ZoneInfo(raw_value)
    except ZoneInfoNotFoundError:
        tz = None

    if tz is not None:
        now = datetime.now(tz)
        offset = now.utcoffset() or timedelta(0)
        offset_minutes = int(offset.total_seconds() // 60)
        return TimezoneInfo(
            name=raw_value,
            offset_minutes=offset_minutes,
            label=_offset_label(offset_minutes),
            resolved_at=now.isoformat(timespec="seconds"),
        )

    try:
        if parsed.startswith("UTC"):
            parsed = parsed[3:]
        if parsed.startswith("GMT"):
            parsed = parsed[3:]
        if not parsed:
            offset_minutes = 0
        else:
            sign = -1 if parsed.startswith("-") else 1
            raw = parsed[1:] if parsed.startswith(("+", "-")) else parsed
            if ":" in raw:
                hours, minutes = raw.split(":", 1)
                offset_minutes = sign * (int(hours) * 60 + int(minutes))
            else:
                offset_minutes = sign * int(raw) * 60
    except ValueError as exc:
        raise ValueError(f"Invalid timezone: {value}") from exc

    if not -14 * 60 <= offset_minutes <= 14 * 60:
        raise ValueError(f"Timezone offset out of range: {value}")

    now = datetime.now(timezone(timedelta(minutes=offset_minutes)))
    return TimezoneInfo(name=raw_value, offset_minutes=offset_minutes, label=_offset_label(offset_minutes), resolved_at=now.isoformat(timespec="seconds"))


def _offset_label(offset_minutes: int) -> str:
    sign = "+" if offset_minutes >= 0 else "-"
    absolute = abs(offset_minutes)
    return f"UTC{sign}{absolute // 60:02d}:{absolute % 60:02d}"
