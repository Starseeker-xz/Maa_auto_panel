from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.utils import dict_value, extract_version, relative_path, version_key, write_text_atomic


CLIENT_ALIASES = {
    "Bilibili": "Official",
}
CURRENT_STAGE_VALUE = "__framework_stage__:current_last"
STAGE_ALIASES_FILE = Path(__file__).with_name("stage_aliases.json")
STAGE_ACTIVITY_URL = "https://api.maa.plus/MaaAssistantArknights/api/gui/StageActivityV2.json"
STAGE_ACTIVITY_REFRESH_SECONDS = 600
STAGE_ACTIVITY_REQUEST_TIMEOUT = (3.05, 8)


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
        self._refresh_lock = threading.Lock()
        self._last_refresh_attempt: float | None = None

    def stage_candidates(
        self,
        *,
        client: str = "Official",
        now: datetime | None = None,
        include_unavailable: bool = False,
    ) -> dict[str, object]:
        now = _as_utc(now)
        effective_client = normalize_client(client)
        errors: list[str] = []
        self._refresh_activity_cache(errors)
        sources = self.sources(effective_client)
        activity_data = _load_json_object(sources.activity_file, errors, label="StageActivityV2")
        display_aliases = _load_stage_aliases(errors)
        core_version = _current_core_version(self.runtime, errors)
        stages = self._build_stage_map(
            activity_data,
            effective_client=effective_client,
            core_version=core_version,
            display_aliases=display_aliases,
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
            "sources": sources.to_dict(self.runtime.repo_root),
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
        display_aliases = _load_stage_aliases(errors)
        core_version = _current_core_version(self.runtime, errors)
        stages = self._build_stage_map(
            activity_data,
            effective_client=effective_client,
            core_version=core_version,
            display_aliases=display_aliases,
        )
        for stage in stage_plan:
            normalized = normalize_stage_plan_value(stage)
            if _stage_info(stages, normalized).is_stage_open(now):
                return to_maa_stage_value(normalized)
        return None

    def sources(self, effective_client: str) -> StageSources:
        activity_candidates = [
            self.runtime.framework_maa_cache_dir / "StageActivityV2.json",
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

    def _refresh_activity_cache(self, errors: list[str]) -> None:
        cache_file = self.runtime.framework_maa_cache_dir / "StageActivityV2.json"
        etag_file = cache_file.with_name(f"{cache_file.name}.etag")
        if _activity_cache_is_fresh(cache_file, etag_file):
            return

        with self._refresh_lock:
            if _activity_cache_is_fresh(cache_file, etag_file):
                return
            attempted_at = time.monotonic()
            if (
                self._last_refresh_attempt is not None
                and attempted_at - self._last_refresh_attempt < STAGE_ACTIVITY_REFRESH_SECONDS
            ):
                return
            self._last_refresh_attempt = attempted_at

            try:
                headers: dict[str, str] = {}
                if cache_file.is_file() and etag_file.is_file():
                    etag = etag_file.read_text(encoding="utf-8").strip()
                    if etag:
                        headers["If-None-Match"] = etag
                response = requests.get(
                    STAGE_ACTIVITY_URL,
                    headers=headers,
                    timeout=STAGE_ACTIVITY_REQUEST_TIMEOUT,
                )
                if response.status_code == 304 and cache_file.is_file():
                    etag_file.touch()
                    return
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("JSON 根节点不是对象")

                write_text_atomic(
                    cache_file,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                )
                etag = response.headers.get("ETag", "").strip()
                if etag:
                    write_text_atomic(etag_file, etag + "\n")
            except Exception as exc:
                errors.append(f"更新 StageActivityV2 失败: {exc}")

    def _build_stage_map(
        self,
        activity_data: dict[str, Any],
        *,
        effective_client: str,
        core_version: str,
        display_aliases: dict[str, str],
    ) -> dict[str, StageInfo]:
        stages = _default_stages()
        client_data = activity_data.get(effective_client)
        if isinstance(client_data, dict):
            resource_collection = _resource_collection(client_data.get("resourceCollection"))
            self._add_activity_stages(stages, client_data, core_version=core_version)
        else:
            resource_collection = StageActivity(is_resource_collection=True)
        _add_permanent_stages(stages, resource_collection, display_aliases)
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
    text = str(value or "").strip()
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


def _add_permanent_stages(
    stages: dict[str, StageInfo],
    resource_collection: StageActivity,
    display_aliases: dict[str, str],
) -> None:
    def permanent(value: str, **kwargs: Any) -> StageInfo:
        return StageInfo(display=display_aliases.get(value, value), value=value, **kwargs)

    permanent = [
        permanent("1-7"),
        permanent("R8-11"),
        permanent("12-17-HARD"),
        permanent("CE-6", open_days_of_week=(1, 3, 5, 6), activity=resource_collection),
        permanent("AP-5", open_days_of_week=(0, 3, 5, 6), activity=resource_collection),
        permanent("CA-5", open_days_of_week=(1, 2, 4, 6), activity=resource_collection),
        permanent("LS-6", open_days_of_week=(), activity=resource_collection),
        permanent("SK-5", open_days_of_week=(0, 2, 4, 5), activity=resource_collection),
        permanent("Annihilation"),
        permanent("PR-A-1", open_days_of_week=(0, 3, 4, 6), activity=resource_collection),
        permanent("PR-A-2", open_days_of_week=(0, 3, 4, 6), activity=resource_collection),
        permanent("PR-B-1", open_days_of_week=(0, 1, 4, 5), activity=resource_collection),
        permanent("PR-B-2", open_days_of_week=(0, 1, 4, 5), activity=resource_collection),
        permanent("PR-C-1", open_days_of_week=(2, 3, 5, 6), activity=resource_collection),
        permanent("PR-C-2", open_days_of_week=(2, 3, 5, 6), activity=resource_collection),
        permanent("PR-D-1", open_days_of_week=(1, 2, 5, 6), activity=resource_collection),
        permanent("PR-D-2", open_days_of_week=(1, 2, 5, 6), activity=resource_collection),
        permanent("OF-1", is_hidden=True),
        permanent("OF-F3", is_hidden=True),
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
    return StageInfo(display=stage, value=stage)


def _load_stage_aliases(errors: list[str], path: Path = STAGE_ALIASES_FILE) -> dict[str, str]:
    loaded = _load_json_object(path, errors, label="关卡别名")
    aliases: dict[str, str] = {}
    invalid = False
    for value, display in loaded.items():
        if not isinstance(value, str) or not value or not isinstance(display, str) or not display:
            invalid = True
            continue
        aliases[value] = display
    if invalid:
        errors.append("关卡别名包含无效条目")
    return aliases


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


def _activity_cache_is_fresh(cache_file: Path, etag_file: Path) -> bool:
    if not cache_file.is_file():
        return False
    timestamps = [cache_file.stat().st_mtime]
    if etag_file.is_file():
        timestamps.append(etag_file.stat().st_mtime)
    return time.time() - max(timestamps) < STAGE_ACTIVITY_REFRESH_SECONDS


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
        runtime.maa_working_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [str(runtime.maa_bin), "version"],
            cwd=runtime.maa_working_dir,
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
