from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from linux_maa.maa.runtime import MaaRuntime


AUTO_PLAN_VALUE = "__linux_maa_runtime__:infrast_plan_index"


@dataclass(frozen=True)
class InfrastPlan:
    index: int
    name: str
    period: list[tuple[str, str]]
    description: str = ""
    description_post: str = ""

    def is_active(self, now: datetime) -> bool:
        current = now.strftime("%H:%M")
        return any(start <= current <= end for start, end in self.period)

    def to_option(self) -> dict[str, object]:
        return {
            "value": str(self.index),
            "label": self.name,
            "period": [[start, end] for start, end in self.period],
            "description": self.description,
            "description_post": self.description_post,
        }


class MaaInfrastService:
    def __init__(self, runtime: MaaRuntime) -> None:
        self.runtime = runtime

    def file_options(self) -> dict[str, object]:
        directory = self.runtime.config_dir / "infrast"
        directory.mkdir(parents=True, exist_ok=True)
        options: list[dict[str, object]] = [
            {
                "value": "",
                "label": "不选择自定义排班文件",
                "path": None,
                "description": "",
            }
        ]
        errors: list[str] = []
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            label = path.name
            description = ""
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    title = loaded.get("title")
                    description_value = loaded.get("description")
                    if isinstance(title, str) and title.strip():
                        label = f"{title.strip()} ({path.name})"
                    if isinstance(description_value, str):
                        description = description_value
            except Exception as exc:
                errors.append(f"读取 {path.name} 失败: {exc}")
            options.append(
                {
                    "value": path.name,
                    "label": label,
                    "path": self._relative_or_none(path),
                    "description": description,
                }
            )
        return {
            "directory": self._relative_or_none(directory),
            "options": options,
            "errors": errors,
        }

    def plan_options(self, *, filename: str, now: datetime | None = None) -> dict[str, object]:
        now = now or datetime.now().astimezone()
        errors: list[str] = []
        plans = self._load_plans(filename, errors)
        active = self._active_plan(plans, now)
        options: list[dict[str, object]] = []
        if any(plan.period for plan in plans):
            active_name = active.name if active else (plans[0].name if plans else "???")
            options.append(
                {
                    "value": AUTO_PLAN_VALUE,
                    "label": f"时间轮换（{active_name}）",
                    "kind": "auto",
                    "selected_plan_index": active.index if active else (plans[0].index if plans else 0),
                }
            )
        options.extend(plan.to_option() for plan in plans)
        return {
            "filename": filename,
            "path": self._relative_or_none(self._resolve_infrast_file(filename)),
            "checked_at": now.isoformat(timespec="seconds"),
            "options": options,
            "errors": errors,
        }

    def resolve_plan_index(self, *, filename: str, value: object, now: datetime | None = None) -> int:
        if not _is_auto_value(value):
            return int(value)  # type: ignore[arg-type]
        now = now or datetime.now().astimezone()
        errors: list[str] = []
        plans = self._load_plans(filename, errors)
        if errors:
            raise ValueError("; ".join(errors))
        if not plans:
            raise ValueError("基建排班文件没有 plans")
        active = self._active_plan(plans, now)
        return active.index if active else plans[0].index

    def _load_plans(self, filename: str, errors: list[str]) -> list[InfrastPlan]:
        path = self._resolve_infrast_file(filename)
        if path is None:
            errors.append("未配置基建排班文件")
            return []
        if not path.is_file():
            errors.append(f"基建排班文件不存在: {filename}")
            return []
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"读取基建排班文件失败: {exc}")
            return []
        raw_plans = loaded.get("plans") if isinstance(loaded, dict) else None
        if not isinstance(raw_plans, list):
            errors.append("基建排班文件缺少 plans 数组")
            return []

        plans: list[InfrastPlan] = []
        for index, raw_plan in enumerate(raw_plans):
            if not isinstance(raw_plan, dict):
                continue
            plans.append(
                InfrastPlan(
                    index=index,
                    name=str(raw_plan.get("name") or f"Plan {index + 1}"),
                    period=_periods(raw_plan.get("period")),
                    description=str(raw_plan.get("description") or ""),
                    description_post=str(raw_plan.get("description_post") or ""),
                )
            )
        return plans

    def _active_plan(self, plans: list[InfrastPlan], now: datetime) -> InfrastPlan | None:
        return next((plan for plan in plans if plan.is_active(now)), None)

    def _resolve_infrast_file(self, filename: str) -> Path | None:
        name = filename.strip()
        if not name:
            return None
        requested = Path(name)
        if requested.is_absolute() or requested.name != name:
            return None
        return self.runtime.config_dir / "infrast" / requested.name

    def _relative_or_none(self, path: Path | None) -> str | None:
        if path is None:
            return None
        try:
            return str(path.relative_to(self.runtime.repo_root))
        except ValueError:
            return str(path)


def _periods(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        return []
    periods: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, list) or len(item) < 2:
            continue
        start = _time_text(item[0])
        end = _time_text(item[1])
        if start and end:
            periods.append((start, end))
    return periods


def _time_text(value: object) -> str:
    text = str(value or "")
    parts = text.split(":")
    if len(parts) < 2:
        return ""
    return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}"


def _is_auto_value(value: object) -> bool:
    return value in {None, "", -1, "__auto__", AUTO_PLAN_VALUE}
