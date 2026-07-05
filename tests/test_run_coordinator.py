from __future__ import annotations

import threading

import pytest

from linux_maa.config.manager import ConfigManager
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.run_coordinator import (
    RUN_PRIORITY_NORMAL,
    RUN_PRIORITY_SCHEDULE_MANUAL,
    RUN_PRIORITY_SCHEDULED,
    RunConflictError,
    RunCoordinator,
    RunLease,
    adb_device_resource,
    adb_device_resources_from_profile,
    schedule_priority,
)
from linux_maa.tools.manager import ToolRunManager


def test_lower_priority_conflict_is_rejected() -> None:
    coordinator = RunCoordinator()
    coordinator.acquire(_lease("schedule-1", RUN_PRIORITY_SCHEDULED))

    with pytest.raises(RunConflictError):
        coordinator.acquire(_lease("manual-1", RUN_PRIORITY_NORMAL))

    coordinator.release("schedule-1")


def test_equal_priority_conflict_waits_until_release() -> None:
    coordinator = RunCoordinator()
    coordinator.acquire(_lease("manual-1", RUN_PRIORITY_NORMAL))
    acquired = threading.Event()

    def acquire_equal() -> None:
        coordinator.acquire(_lease("tool-1", RUN_PRIORITY_NORMAL))
        acquired.set()

    thread = threading.Thread(target=acquire_equal)
    thread.start()

    assert not acquired.wait(0.05)
    coordinator.release("manual-1")
    assert acquired.wait(2)
    coordinator.release("tool-1")
    thread.join(timeout=2)


def test_higher_priority_conflict_requests_stop_and_waits() -> None:
    coordinator = RunCoordinator()
    stop_requested = threading.Event()
    coordinator.acquire(_lease("manual-1", RUN_PRIORITY_NORMAL, request_stop=stop_requested.set))
    acquired = threading.Event()

    def acquire_high_priority() -> None:
        coordinator.acquire(_lease("schedule-1", RUN_PRIORITY_SCHEDULED))
        acquired.set()

    thread = threading.Thread(target=acquire_high_priority)
    thread.start()

    assert stop_requested.wait(2)
    assert not acquired.wait(0.05)
    coordinator.release("manual-1")
    assert acquired.wait(2)
    coordinator.release("schedule-1")
    thread.join(timeout=2)


def test_preemption_uses_force_stop_callback_after_grace() -> None:
    coordinator = RunCoordinator()
    stop_requested = threading.Event()
    force_requested = threading.Event()
    coordinator.acquire(
        _lease(
            "manual-1",
            RUN_PRIORITY_NORMAL,
            request_stop=stop_requested.set,
            request_force_stop=force_requested.set,
            force_after_seconds=0.05,
        )
    )
    acquired = threading.Event()

    def acquire_high_priority() -> None:
        coordinator.acquire(_lease("schedule-1", RUN_PRIORITY_SCHEDULED))
        acquired.set()

    thread = threading.Thread(target=acquire_high_priority)
    thread.start()

    assert stop_requested.wait(2)
    assert force_requested.wait(2)
    assert not acquired.wait(0.05)
    coordinator.release("manual-1")
    assert acquired.wait(2)
    coordinator.release("schedule-1")
    thread.join(timeout=2)


def test_schedule_priorities_and_profile_adb_resource() -> None:
    resources = adb_device_resources_from_profile({"connection": {"address": " 127.0.0.1:5555 "}})

    assert resources[0].identifier == "127.0.0.1:5555"
    assert schedule_priority("schedule") == RUN_PRIORITY_SCHEDULED
    assert schedule_priority("manual") == RUN_PRIORITY_SCHEDULE_MANUAL
    assert RUN_PRIORITY_SCHEDULED > RUN_PRIORITY_SCHEDULE_MANUAL > RUN_PRIORITY_NORMAL


def test_tool_start_rejects_higher_priority_occupied_device(tmp_path) -> None:
    runtime = MaaRuntime(tmp_path)
    coordinator = RunCoordinator()
    coordinator.acquire(_lease("schedule-1", RUN_PRIORITY_SCHEDULED, address="127.0.0.1:5555"))
    manager = ToolRunManager(runtime, ConfigManager(runtime), run_coordinator=coordinator)

    with pytest.raises(RunConflictError):
        manager.start("game-update", {"address": "127.0.0.1:5555"})

    assert coordinator.occupied_resources()[0]["run_id"] == "schedule-1"
    coordinator.release("schedule-1")


def _lease(
    run_id: str,
    priority: int,
    *,
    address: str = "127.0.0.1:5555",
    request_stop=None,
    request_force_stop=None,
    force_after_seconds: float | None = None,
) -> RunLease:
    resource = adb_device_resource(address)
    assert resource is not None
    return RunLease(
        run_id=run_id,
        kind="test",
        title=run_id,
        priority=priority,
        resources=(resource,),
        request_stop=request_stop,
        request_force_stop=request_force_stop,
        force_after_seconds=force_after_seconds,
    )
