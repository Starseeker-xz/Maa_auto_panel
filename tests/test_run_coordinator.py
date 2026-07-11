from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from maa_auto_panel.config.app_settings import FrameworkSettingsManager
from maa_auto_panel.config.manager import ConfigManager
from maa_auto_panel.maa.maintenance import MaintenanceActionManager
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.coordinator import (
    RunConflictError,
    RunCoordinator,
    RunLease,
)
from maa_auto_panel.run_resources import (
    RUN_PRIORITY_NORMAL,
    RUN_PRIORITY_SCHEDULE_MANUAL,
    RUN_PRIORITY_SCHEDULED,
    RESOURCE_ACCESS_EXCLUSIVE,
    RESOURCE_ACCESS_SHARED,
    RunResource,
    adb_device_resource,
    adb_device_resources_from_profile,
    maa_runtime_resource,
    maa_run_resources_from_profile,
    resources_conflict,
    schedule_priority,
)
from maa_auto_panel.tools.manager import ToolRunManager


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


def test_non_preemptible_lower_priority_lease_blocks_higher_priority() -> None:
    coordinator = RunCoordinator()
    resource = maa_runtime_resource(exclusive=True)
    coordinator.acquire(
        RunLease(
            "maintenance-1",
            "maintenance",
            "Runtime update",
            RUN_PRIORITY_NORMAL,
            resources=(resource,),
            preemptible=False,
        )
    )

    with pytest.raises(RunConflictError) as exc_info:
        coordinator.acquire(
            RunLease(
                "schedule-1",
                "schedule",
                "Scheduled run",
                RUN_PRIORITY_SCHEDULED,
                resources=(maa_runtime_resource(),),
            )
        )

    assert exc_info.value.blockers[0].run_id == "maintenance-1"


def test_schedule_priorities_and_profile_adb_resource() -> None:
    resources = adb_device_resources_from_profile({"connection": {"address": " 127.0.0.1:5555 "}})

    assert resources[0].identifier == "127.0.0.1:5555"
    assert schedule_priority("schedule") == RUN_PRIORITY_SCHEDULED
    assert schedule_priority("manual") == RUN_PRIORITY_SCHEDULE_MANUAL
    assert RUN_PRIORITY_SCHEDULED > RUN_PRIORITY_SCHEDULE_MANUAL > RUN_PRIORITY_NORMAL

    maa_resources = maa_run_resources_from_profile({"connection": {"address": "127.0.0.1:5555"}})
    assert [(resource.kind, resource.access) for resource in maa_resources] == [
        ("integration-runtime", RESOURCE_ACCESS_SHARED),
        ("adb-device", RESOURCE_ACCESS_EXCLUSIVE),
    ]


def test_global_resource_wait_timeout_setting_round_trips(tmp_path) -> None:
    settings = FrameworkSettingsManager(MaaRuntime(tmp_path))
    assert settings.resource_wait_timeout_seconds() == 300

    data = settings.read()["data"]
    data["framework"]["run_resources"]["wait_timeout_seconds"] = 45
    data["theme"] = {"mode": "dark", "color": "rose"}
    settings.write(data)

    assert settings.resource_wait_timeout_seconds() == 45
    assert "theme" not in settings.read()["data"]


def test_shared_runtime_claims_can_run_together() -> None:
    coordinator = RunCoordinator()
    coordinator.acquire(_resource_lease("maa-1", maa_runtime_resource()))
    coordinator.acquire(_resource_lease("maa-2", maa_runtime_resource()))

    occupied = coordinator.occupied_resources()
    assert len(occupied) == 2
    assert occupied[0]["resources"][0]["access"] == RESOURCE_ACCESS_SHARED


def test_exclusive_runtime_claim_conflicts_with_shared_claim() -> None:
    shared = maa_runtime_resource()
    exclusive = maa_runtime_resource(exclusive=True)

    assert shared.access == RESOURCE_ACCESS_SHARED
    assert exclusive.access == RESOURCE_ACCESS_EXCLUSIVE
    assert not resources_conflict(shared, shared)
    assert resources_conflict(shared, exclusive)
    assert resources_conflict(exclusive, shared)
    assert resources_conflict(exclusive, exclusive)


def test_different_runtime_identifiers_do_not_conflict() -> None:
    maa = maa_runtime_resource(exclusive=True)
    other = RunResource("integration-runtime", "other", RESOURCE_ACCESS_EXCLUSIVE)

    assert not resources_conflict(maa, other)


def test_maintenance_update_claims_runtime_exclusively(tmp_path, monkeypatch) -> None:
    manager = MaintenanceActionManager(MaaRuntime(tmp_path))
    captured = {}

    def capture_start(plan, *, run_id=None):
        captured["plan"] = plan
        return SimpleNamespace(id=run_id)

    monkeypatch.setattr(manager.runs, "start", capture_start)
    manager.start("core-update")

    resources = captured["plan"].resources
    assert len(resources) == 1
    assert resources[0] == maa_runtime_resource(exclusive=True)
    assert captured["plan"].preemptible is False


def test_tool_start_records_higher_priority_resource_conflict_as_failed_run(tmp_path) -> None:
    runtime = MaaRuntime(tmp_path)
    coordinator = RunCoordinator()
    coordinator.acquire(_lease("schedule-1", RUN_PRIORITY_SCHEDULED, address="127.0.0.1:5555"))
    manager = ToolRunManager(runtime, ConfigManager(runtime), run_coordinator=coordinator)

    state = manager.start("game-update", {"address": "127.0.0.1:5555"})
    assert state.thread is not None
    state.thread.join(timeout=2)

    assert state.status == "failed"
    assert len(state.retries) == 1
    assert state.retries[0].status == "failed"
    assert any("运行资源申请失败" in str(entry.get("title")) for entry in state.retries[0].log.entries())
    stored = manager.runs.store.run(state.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.retry_count == 1
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


def _resource_lease(run_id: str, resource: RunResource) -> RunLease:
    return RunLease(
        run_id=run_id,
        kind="test",
        title=run_id,
        priority=RUN_PRIORITY_NORMAL,
        resources=(resource,),
    )
