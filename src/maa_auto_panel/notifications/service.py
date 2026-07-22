from __future__ import annotations

import threading
import tomllib
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Literal, Protocol

from maa_auto_panel.errors import InvalidRequest
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.state import LiveRun
from maa_auto_panel.time_utils import server_now_iso
from maa_auto_panel.utils import write_text_atomic


Severity = Literal["info", "success", "warning", "error"]


@dataclass(frozen=True)
class NotificationTagSpec:
    id: str
    title: str
    description: str
    default_toast: bool = True
    default_external: bool = False
    important: bool = False
    replay_toast: bool = False


NOTIFICATION_TAGS = (
    NotificationTagSpec("runtime.maa.missing", "MAA Runtime 不完整", "maa-cli 或 MaaCore 不存在时通知", important=True, replay_toast=True),
    NotificationTagSpec("runtime.maa.update_available", "MAA Runtime 可更新", "maa-cli 或 MaaCore 存在更新时通知", important=True, replay_toast=True),
    NotificationTagSpec("run.maa.manual.finished", "手动 MAA 运行完成", "主界面手动运行成功或失败时通知"),
    NotificationTagSpec("run.maa.schedule.auto.finished", "定时 MAA 运行完成", "定时器自动触发的运行成功或失败时通知"),
    NotificationTagSpec("run.maa.schedule.manual.finished", "手动触发定时运行完成", "从定时页面手动触发的运行成功或失败时通知"),
)
TAG_BY_ID = {spec.id: spec for spec in NOTIFICATION_TAGS}


@dataclass(frozen=True)
class NotificationEvent:
    id: str
    sequence: int
    tag: str
    severity: Severity
    title: str
    message: str
    created_at: str
    toast: bool
    important: bool
    replay_toast: bool
    data: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sequence": self.sequence,
            "tag": self.tag,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "created_at": self.created_at,
            "toast": self.toast,
            "important": self.important,
            "replay_toast": self.replay_toast,
            "data": dict(self.data),
        }


class ExternalNotificationSender(Protocol):
    """Future external channel boundary. Implementations must handle their own delivery failures."""

    def send(self, event: NotificationEvent) -> None: ...


class NullExternalNotificationSender:
    def send(self, event: NotificationEvent) -> None:
        return None


class NotificationSettingsManager:
    def __init__(self, runtime: MaaRuntime) -> None:
        self.path = runtime.framework_config_dir / "notifications.toml"

    def read_rules(self) -> dict[str, dict[str, bool]]:
        configured: dict[str, object] = {}
        if self.path.exists():
            data = tomllib.loads(self.path.read_text(encoding="utf-8"))
            value = data.get("tags")
            configured = value if isinstance(value, dict) else {}
        rules: dict[str, dict[str, bool]] = {}
        for spec in NOTIFICATION_TAGS:
            value = configured.get(spec.id)
            item = value if isinstance(value, dict) else {}
            rules[spec.id] = {
                "toast": bool(item.get("toast", spec.default_toast)),
                "external": bool(item.get("external", spec.default_external)),
            }
        return rules

    def response(self) -> dict[str, object]:
        rules = self.read_rules()
        return {
            "file": {"path": str(self.path), "exists": self.path.exists()},
            "tags": [
                {
                    "id": spec.id,
                    "title": spec.title,
                    "description": spec.description,
                    "important": spec.important,
                    "replay_toast": spec.replay_toast,
                    **rules[spec.id],
                }
                for spec in NOTIFICATION_TAGS
            ],
            "external_channels_available": False,
        }

    def write(self, payload: dict[str, object]) -> dict[str, object]:
        submitted = payload.get("tags")
        submitted_tags = submitted if isinstance(submitted, list) else []
        by_id = {
            str(item.get("id")): item
            for item in submitted_tags
            if isinstance(item, dict) and str(item.get("id")) in TAG_BY_ID
        }
        current = self.read_rules()
        lines = ["# Notification delivery policy. Tags are stable event categories."]
        for spec in NOTIFICATION_TAGS:
            item = by_id.get(spec.id, {})
            toast = bool(item.get("toast", current[spec.id]["toast"]))
            external = bool(item.get("external", current[spec.id]["external"]))
            lines.extend([
                "",
                f'[tags."{spec.id}"]',
                f"toast = {'true' if toast else 'false'}",
                f"external = {'true' if external else 'false'}",
            ])
        write_text_atomic(self.path, "\n".join(lines) + "\n")
        return self.response()


class NotificationService:
    def __init__(
        self,
        runtime: MaaRuntime,
        settings: NotificationSettingsManager | None = None,
        external_sender: ExternalNotificationSender | None = None,
        *,
        max_events: int = 100,
    ) -> None:
        self.runtime = runtime
        self.settings = settings or NotificationSettingsManager(runtime)
        self.external_sender = external_sender or NullExternalNotificationSender()
        self._events: deque[NotificationEvent] = deque(maxlen=max_events)
        self._sequence = 0
        self._conditions: dict[str, str] = {}
        self._condition = threading.Condition()

    def inspect_runtime_presence(self) -> None:
        missing: list[str] = []
        if not self.runtime.maa_bin.is_file():
            missing.append("maa-cli")
        core_library = self.runtime.data_home / "maa" / "lib" / "libMaaCore.so"
        if not core_library.is_file():
            missing.append("MaaCore")
        signature = ",".join(missing)
        if not signature:
            self._conditions.pop("runtime.maa.missing", None)
            return
        if self._conditions.get("runtime.maa.missing") == signature:
            return
        self._conditions["runtime.maa.missing"] = signature
        self.publish(
            "runtime.maa.missing",
            "error",
            "MAA Runtime 不完整",
            f"缺少：{'、'.join(missing)}。MAA 运行暂不可用。",
            {"missing_components": missing},
        )

    def observe_update_info(self, info: dict[str, object]) -> None:
        latest = info.get("latest")
        latest_items = latest if isinstance(latest, dict) else {}
        updates = [
            label
            for key, label in (("maa_cli", "maa-cli"), ("maa_core", "MaaCore"))
            if isinstance(latest_items.get(key), dict) and latest_items[key].get("update_available") is True
        ]
        signature = ",".join(updates)
        if not signature:
            self._conditions.pop("runtime.maa.update_available", None)
            return
        if self._conditions.get("runtime.maa.update_available") == signature:
            return
        self._conditions["runtime.maa.update_available"] = signature
        self.publish(
            "runtime.maa.update_available",
            "info",
            "MAA Runtime 可更新",
            f"可更新组件：{'、'.join(updates)}。",
            {"components": updates},
        )

    def notify_run_finished(self, run: LiveRun) -> None:
        if run.status == "stopped":
            return
        if run.kind == "manual":
            tag = "run.maa.manual.finished"
            title = "手动 MAA 运行完成"
        elif run.kind == "schedule":
            manual = run.metadata.get("trigger") == "manual"
            tag = "run.maa.schedule.manual.finished" if manual else "run.maa.schedule.auto.finished"
            title = "手动触发定时运行完成" if manual else "定时 MAA 运行完成"
        else:
            return
        succeeded = run.status == "succeeded"
        status_text = "成功" if succeeded else "失败"
        self.publish(
            tag,
            "success" if succeeded else "error",
            title,
            f"{run.title}运行{status_text}，共 {len(run.retries)} 次尝试。",
            {"run_id": run.id, "status": run.status, "retry_count": len(run.retries), **dict(run.metadata)},
        )

    def publish(
        self,
        tag: str,
        severity: Severity,
        title: str,
        message: str,
        data: dict[str, object] | None = None,
    ) -> NotificationEvent:
        if tag not in TAG_BY_ID:
            raise InvalidRequest(f"Unknown notification tag: {tag}")
        rules = self.settings.read_rules()[tag]
        spec = TAG_BY_ID[tag]
        with self._condition:
            self._sequence += 1
            important = spec.important or severity in {"warning", "error"}
            replay_toast = spec.replay_toast or severity != "success"
            event = NotificationEvent(
                uuid.uuid4().hex,
                self._sequence,
                tag,
                severity,
                title,
                message,
                server_now_iso(),
                rules["toast"],
                important,
                replay_toast,
                data or {},
            )
            self._events.append(event)
            self._condition.notify_all()
        if rules["external"]:
            self.external_sender.send(event)
        return event

    def events_after(self, sequence: int) -> list[dict[str, object]]:
        with self._condition:
            return [event.to_dict() for event in self._events if event.sequence > sequence]

    def wait_for_change(self, sequence: int, timeout: float | None = None) -> int:
        with self._condition:
            self._condition.wait_for(lambda: self._sequence > sequence, timeout=timeout)
            return self._sequence

    def latest_sequence(self) -> int:
        with self._condition:
            return self._sequence
