from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from linux_maa.settings import DEFAULT_DEVICE_SERIAL
from linux_maa.utils import dict_value


RUN_PRIORITY_NORMAL = 10
RUN_PRIORITY_SCHEDULE_MANUAL = 20
RUN_PRIORITY_SCHEDULED = 30

RUN_PRIORITY_VALUES = {
    "normal": RUN_PRIORITY_NORMAL,
    "schedule.manual": RUN_PRIORITY_SCHEDULE_MANUAL,
    "schedule.auto": RUN_PRIORITY_SCHEDULED,
}


@dataclass(frozen=True)
class RunResource:
    """A resource claimed by a live run. Conflict rules stay outside run managers."""

    kind: str
    identifier: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "identifier": self.identifier}


class RunResourcePolicy(Protocol):
    def priority_value(self, name: str) -> int: ...

    def conflicts(self, left: RunResource, right: RunResource) -> bool: ...


class DefaultRunResourcePolicy:
    def priority_value(self, name: str) -> int:
        return RUN_PRIORITY_VALUES.get(name, RUN_PRIORITY_NORMAL)

    def conflicts(self, left: RunResource, right: RunResource) -> bool:
        return resources_conflict(left, right)


def default_run_resource_policy() -> DefaultRunResourcePolicy:
    return DefaultRunResourcePolicy()


def adb_device_resource(address: object) -> RunResource | None:
    normalized = str(address or "").strip()
    if not normalized:
        return None
    return RunResource(kind="adb-device", identifier=normalized)


def adb_device_resources_from_profile(profile_data: dict[str, object]) -> tuple[RunResource, ...]:
    connection = dict_value(profile_data.get("connection"))
    resource = adb_device_resource(connection.get("address") or DEFAULT_DEVICE_SERIAL)
    return (resource,) if resource is not None else ()


def schedule_priority(trigger: str) -> int:
    return RUN_PRIORITY_SCHEDULED if trigger == "schedule" else RUN_PRIORITY_SCHEDULE_MANUAL


def resources_conflict(left: RunResource, right: RunResource) -> bool:
    if left.kind == "adb-device" and right.kind == "adb-device":
        return left.identifier == right.identifier
    return left.kind == right.kind and left.identifier == right.identifier
