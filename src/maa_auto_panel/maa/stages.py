from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.utils import dict_value, extract_version, relative_path, version_key


CLIENT_ALIASES = {
    "Bilibili": "Official",
}
CURRENT_STAGE_VALUE = "__framework_stage__:current_last"


@dataclass(frozen=True)
class StageActivity:
    """Limited-time stage activity with start/expire times and resource-collection flag."""
    tip: str = ""
    stage_name: str = ""
    utc_start_time: datetime | None = None
    utc_expire_time: datetime | None = None
    is_resource_collection: bool = False

    def being_open(self, now: datetime) -> bool:
        return not self.not_open_yet(now) and not self.is_expired(now)

    def is_expired(self, now: datetime) -> bool:
        return self.utc_expire_time is not None and now >= self.utc_expire_time

    def not_open_yet(self, now: datetime) -> bool:
        return self.utc_start_time is not None and now <= self.utc_start_time

    def to_dict(self, now: datetime) -> dict[str, object]:
        return {
            "tip": self.tip,
            "stage_name": self.stage_name,
            "utc_start_time": self.utc_start_time.isoformat() if self.utc_start_time else None,
            "utc_expire_time": self.utc_expire_time.isoformat() if self.utc_expire_time else None,
            "is_resource_collection": self.is_resource_collection,
            "being_open": self.being_open(now),
            "is_expired": self.is_expired(now),
            "not_open_yet": self.not_open_yet(now),
        }


@dataclass(frozen=True)
class StageInfo:
    """A single farmable stage: display name, drop info, open-day schedule, activity, version gate."""
    display: str
    value: str
    drop: str | None = None
    open_days_of_week: tuple[int, ...] | None = None
    activity: StageActivity | None = None
    is_hidden: bool = False
    is_low_version: bool = False
    minimum_required: str | None = None

    def is_stage_open(self, now: datetime) -> bool:
        if self.activity is not None:
            if self.activity.being_open(now):
                return True
            if not self.activity.is_resource_collection:
                return False

        if self.open_days_of_week:
            return now.weekday() in self.open_days_of_week
        return True

    def is_stage_open_or_will_open(self, now: datetime) -> bool:
        if self.activity is None:
            return True
        return not self.activity.is_expired(now) or self.activity.is_resource_collection

    def to_dict(self, now: datetime) -> dict[str, object]:
        return {
            "display": self.display,
            "value": self.value,
            "maa_value": to_maa_stage_value(self.value),
            "drop": self.drop,
            "open_days_of_week": list(self.open_days_of_week) if self.open_days_of_week else [],
            "activity": self.activity.to_dict(now) if self.activity else None,
            "is_hidden": self.is_hidden,
            "is_open": self.is_stage_open(now),
            "is_open_or_will_open": self.is_stage_open_or_will_open(now),
            "is_low_version": self.is_low_version,
            "minimum_required": self.minimum_required,
        }


@dataclass(frozen=True)
class StageSources:
    activity_file: Path | None
    tasks_file: Path | None
    global_tasks_file: Path | None

    def to_dict(self, repo_root: Path) -> dict[str, object]:
        return {
            "activity_file": _relative_or_none(self.activity_file, repo_root),
            "tasks_file": _relative_or_none(self.tasks_file, repo_root),
            "global_tasks_file": _relative_or_none(self.global_tasks_file, repo_root),
        }


class MaaStageService:
    """Backend copy of MAA GUI's Fight stage candidate list rules."""

    def __init__(self, runtime: MaaRuntime) -> None:
        self.runtime = runtime

    def stage_candidates(
        self,
        *,
        client: str = "Official",
        now: datetime | None = None,
        include_unavailable: bool = False,
    ) -> dict[str, object]:
        now = _as_utc(now)
        effective_client = normalize_client(client)
        sources = self.sources(effective_client)
        errors: list[str] = []
        activity_data = _load_json_object(sources.activity_file, errors, label="StageActivityV2")
        core_version = _current_core_version(self.runtime, errors)
        stages = self._build_stage_map(
            activity_data,
            effective_client=effective_client,
            core_version=core_version,
        )
        values = [
            stage.to_dict(now)
            for stage in stages.values()
            if not stage.is_hidden and (include_unavailable or stage.is_stage_open(now))
        ]
        return {
            "client": client,
            "effective_client": effective_client,
            "checked_at": now.isoformat(),
            "maa_core_version": core_version,
            "sources": sources.to_dict(self.runtime.data_root),
            "stages": values,
            "errors": errors,
        }

    def resolve_first_open_stage(
        self,
        stage_plan: list[str],
        *,
        client: str = "Official",
        now: datetime | None = None,
    ) -> str | None:
        now = _as_utc(now)
        effective_client = normalize_client(client)
        sources = self.sources(effective_client)
        errors: list[str] = []
        activity_data = _load_json_object(sources.activity_file, errors, label="StageActivityV2")
        core_version = _current_core_version(self.runtime, errors)
        stages = self._build_stage_map(
            activity_data,
            effective_client=effective_client,
            core_version=core_version,
        )
        for stage in stage_plan:
            normalized = normalize_stage_plan_value(stage)
            if _stage_info(stages, normalized).is_stage_open(now):
                return to_maa_stage_value(normalized)
        return None

    def sources(self, effective_client: str) -> StageSources:
        activity_candidates = [
            self.runtime.cache_home / "maa" / "StageActivityV2.json",
            self.runtime.data_home / "maa" / "StageActivityV2.json",
        ]
        tasks_file = self.runtime.data_home / "maa" / "resource" / "tasks" / "tasks.json"
        global_tasks_file = (
            self.runtime.data_home / "maa" / "resource" / "global" / effective_client / "resource" / "tasks" / "tasks.json"
        )
        return StageSources(
            activity_file=next((path for path in activity_candidates if path.is_file()), None),
            tasks_file=tasks_file if tasks_file.is_file() else None,
            global_tasks_file=global_tasks_file if global_tasks_file.is_file() else None,
        )

    def _build_stage_map(
        self,
        activity_data: dict[str, Any],
        *,
        effective_client: str,
        core_version: str,
    ) -> dict[str, StageInfo]:
        stages = _default_stages()
        client_data = activity_data.get(effective_client)
        if isinstance(client_data, dict):
            resource_collection = _resource_collection(client_data.get("resourceCollection"))
            self._add_activity_stages(stages, client_data, core_version=core_version)
        else:
            resource_collection = StageActivity(is_resource_collection=True)
        _add_permanent_stages(stages, resource_collection)
        return stages

    def _add_activity_stages(
        self,
        stages: dict[str, StageInfo],
        client_data: dict[str, Any],
        *,
        core_version: str,
    ) -> None:
        side_story = client_data.get("sideStoryStage")
        if not isinstance(side_story, dict):
            return

        for group in side_story.values():
            if not isinstance(group, dict):
                continue
            activity_token = dict_value(group.get("Activity") or group.get("activity"))
            group_minimum = str(group.get("MinimumRequired") or group.get("minimumRequired") or "")
            stage_list = group.get("Stages") or group.get("stages")
            if not isinstance(stage_list, list):
                continue

            for item in stage_list:
                if not isinstance(item, dict):
                    continue
                minimum = str(item.get("MinimumRequired") or group_minimum or "")
                is_low_version = bool(minimum and core_version and version_key(core_version) < version_key(minimum))
                display = str(item.get("Display") or "")
                value = str(item.get("Value") or "")
                if not display or not value:
                    continue
                activity = _activity_info(dict_value(item.get("Activity")) or activity_token)
                stages.setdefault(
                    display,
                    StageInfo(
                        display=display,
                        value=value,
                        drop=str(item.get("Drop")) if item.get("Drop") is not None else None,
                        activity=activity,
                        is_low_version=is_low_version,
                        minimum_required=minimum or None,
                    ),
                )


def normalize_client(client: str) -> str:
    value = client.strip() or "Official"
    return CLIENT_ALIASES.get(value, value)


def normalize_stage_plan_value(value: object) -> str:
    text = str(value or "")
    return CURRENT_STAGE_VALUE if text == "" else text


def to_maa_stage_value(value: object) -> str:
    text = normalize_stage_plan_value(value)
    return "" if text == CURRENT_STAGE_VALUE else text


def _default_stages() -> dict[str, StageInfo]:
    return {
        CURRENT_STAGE_VALUE: StageInfo(display="当前/上次", value=CURRENT_STAGE_VALUE),
        "Pormpt1": StageInfo(display="Pormpt1", value="Pormpt1", open_days_of_week=(0,), is_hidden=True),
        "Pormpt2": StageInfo(display="Pormpt2", value="Pormpt2", open_days_of_week=(6,), is_hidden=True),
    }


def _add_permanent_stages(stages: dict[str, StageInfo], resource_collection: StageActivity) -> None:
    permanent = [
        StageInfo(display="1-7", value="1-7"),
        StageInfo(display="R8-11", value="R8-11"),
        StageInfo(display="12-17-HARD", value="12-17-HARD"),
        StageInfo(display="CE-6", value="CE-6", open_days_of_week=(1, 3, 5, 6), activity=resource_collection),
        StageInfo(display="AP-5", value="AP-5", open_days_of_week=(0, 3, 5, 6), activity=resource_collection),
        StageInfo(display="CA-5", value="CA-5", open_days_of_week=(1, 2, 4, 6), activity=resource_collection),
        StageInfo(display="LS-6", value="LS-6", open_days_of_week=(), activity=resource_collection),
        StageInfo(display="SK-5", value="SK-5", open_days_of_week=(0, 2, 4, 5), activity=resource_collection),
        StageInfo(display="剿灭模式", value="Annihilation"),
        StageInfo(display="PR-A-1", value="PR-A-1", open_days_of_week=(0, 3, 4, 6), activity=resource_collection),
        StageInfo(display="PR-A-2", value="PR-A-2", open_days_of_week=(0, 3, 4, 6), activity=resource_collection),
        StageInfo(display="PR-B-1", value="PR-B-1", open_days_of_week=(0, 1, 4, 5), activity=resource_collection),
        StageInfo(display="PR-B-2", value="PR-B-2", open_days_of_week=(0, 1, 4, 5), activity=resource_collection),
        StageInfo(display="PR-C-1", value="PR-C-1", open_days_of_week=(2, 3, 5, 6), activity=resource_collection),
        StageInfo(display="PR-C-2", value="PR-C-2", open_days_of_week=(2, 3, 5, 6), activity=resource_collection),
        StageInfo(display="PR-D-1", value="PR-D-1", open_days_of_week=(1, 2, 5, 6), activity=resource_collection),
        StageInfo(display="PR-D-2", value="PR-D-2", open_days_of_week=(1, 2, 5, 6), activity=resource_collection),
        StageInfo(display="OF-1", value="OF-1", is_hidden=True),
        StageInfo(display="OF-F3", value="OF-F3", is_hidden=True),
    ]
    for stage in permanent:
        stages.setdefault(stage.display, stage)


def _stage_info(stages: dict[str, StageInfo], stage: str) -> StageInfo:
    stage = normalize_stage_plan_value(stage)
    if stage in stages:
        return stages[stage]
    for info in stages.values():
        if info.value == stage:
            return info
    if stage and re.match(r"^[A-Za-z]{2}-\d{1,2}$", stage):
        closed_activity = StageActivity(
            utc_start_time=datetime.min.replace(tzinfo=timezone.utc),
            utc_expire_time=datetime.min.replace(tzinfo=timezone.utc),
        )
        return StageInfo(display=stage, value=stage, activity=closed_activity)
    return StageInfo(display=stage, value=stage)


def _resource_collection(token: object) -> StageActivity:
    data = dict_value(token)
    if not data:
        return StageActivity(is_resource_collection=True)
    return StageActivity(
        tip=str(data.get("Tip") or ""),
        utc_start_time=_parse_activity_time(data, "UtcStartTime"),
        utc_expire_time=_parse_activity_time(data, "UtcExpireTime"),
        is_resource_collection=True,
    )


def _activity_info(data: dict[str, Any]) -> StageActivity:
    return StageActivity(
        tip=str(data.get("Tip") or ""),
        stage_name=str(data.get("StageName") or ""),
        utc_start_time=_parse_activity_time(data, "UtcStartTime"),
        utc_expire_time=_parse_activity_time(data, "UtcExpireTime"),
    )


def _parse_activity_time(data: dict[str, Any], key: str) -> datetime | None:
    value = str(data.get(key) or "")
    if not value:
        return None
    parsed = datetime.strptime(value, "%Y/%m/%d %H:%M:%S")
    offset_hours = int(data.get("TimeZone") or 0)
    return parsed.replace(tzinfo=timezone.utc) - timedelta(hours=offset_hours)


def _load_json_object(path: Path | None, errors: list[str], *, label: str) -> dict[str, Any]:
    if path is None:
        errors.append(f"{label} 文件不存在")
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"读取 {label} 失败: {exc}")
        return {}
    if not isinstance(loaded, dict):
        errors.append(f"{label} 根节点不是对象")
        return {}
    return loaded


def _current_core_version(runtime: MaaRuntime, errors: list[str]) -> str:
    try:
        proc = subprocess.run(
            [str(runtime.maa_bin), "version"],
            cwd=runtime.repo_root,
            env=runtime.env(),
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except Exception as exc:
        errors.append(f"读取 MaaCore 版本失败: {exc}")
        return ""
    if proc.returncode != 0:
        errors.append(f"读取 MaaCore 版本失败: {proc.stderr or proc.stdout}".strip())
        return ""
    for line in proc.stdout.splitlines():
        if line.lower().startswith("maacore"):
            return _extract_version(line)
    errors.append("maa version 输出中没有 MaaCore 行")
    return ""


def _extract_version(line: str) -> str:
    return extract_version(line)


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _relative_or_none(path: Path | None, repo_root: Path) -> str | None:
    if path is None:
        return None
    return relative_path(path, repo_root)
