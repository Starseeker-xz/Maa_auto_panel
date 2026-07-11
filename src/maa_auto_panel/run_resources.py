from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from maa_auto_panel.settings import DEFAULT_DEVICE_SERIAL
from maa_auto_panel.utils import dict_value


RUN_PRIORITY_NORMAL = 10
RUN_PRIORITY_SCHEDULE_MANUAL = 20
RUN_PRIORITY_SCHEDULED = 30

RUN_PRIORITY_VALUES = {
    "normal": RUN_PRIORITY_NORMAL,
    "schedule.manual": RUN_PRIORITY_SCHEDULE_MANUAL,
    "schedule.auto": RUN_PRIORITY_SCHEDULED,
}

RESOURCE_ACCESS_SHARED = "shared"
RESOURCE_ACCESS_EXCLUSIVE = "exclusive"
RESOURCE_ACCESS_VALUES = {RESOURCE_ACCESS_SHARED, RESOURCE_ACCESS_EXCLUSIVE}


@dataclass(frozen=True)
class RunResource:
    """A resource claimed by a live run. Conflict rules stay outside run managers."""

    kind: str
    identifier: str
    access: str = RESOURCE_ACCESS_EXCLUSIVE

    def __post_init__(self) -> None:
        if self.access not in RESOURCE_ACCESS_VALUES:
            raise ValueError(f"Unsupported resource access mode: {self.access}")

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "identifier": self.identifier, "access": self.access}


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


def maa_runtime_resource(*, exclusive: bool = False) -> RunResource:
    return RunResource(
        kind="integration-runtime",
        identifier="maa",
        access=RESOURCE_ACCESS_EXCLUSIVE if exclusive else RESOURCE_ACCESS_SHARED,
    )


def adb_device_resources_from_profile(profile_data: dict[str, object]) -> tuple[RunResource, ...]:
    connection = dict_value(profile_data.get("connection"))
    resource = adb_device_resource(connection.get("address") or DEFAULT_DEVICE_SERIAL)
    return (resource,) if resource is not None else ()


def maa_run_resources_from_profile(profile_data: dict[str, object]) -> tuple[RunResource, ...]:
    """Claims needed while a MAA process reads its runtime and controls a device."""
    return (maa_runtime_resource(), *adb_device_resources_from_profile(profile_data))


def schedule_priority(trigger: str) -> int:
    return RUN_PRIORITY_SCHEDULED if trigger == "schedule" else RUN_PRIORITY_SCHEDULE_MANUAL


def resources_conflict(left: RunResource, right: RunResource) -> bool:
    same_resource = left.kind == right.kind and left.identifier == right.identifier
    return same_resource and RESOURCE_ACCESS_EXCLUSIVE in {left.access, right.access}
