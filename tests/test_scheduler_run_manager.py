from pathlib import Path

from maa_auto_panel.diagnostics import Diagnostics
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.contracts import RunStartPlan
from maa_auto_panel.run_manager.manager import GenericRunManager
from maa_auto_panel.run_manager.store import RunStateStore
from maa_auto_panel.scheduler.models import ScheduleConfig, ScheduleEntry, TaskPolicy
from maa_auto_panel.scheduler.service import ScheduledMaaRunCallbacks, _schedule_log_profile
from maa_auto_panel.scheduler.state import SchedulerStateStore


def test_scheduled_driver_skip_persists_sealed_retry(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime.layout.framework, runtime.path_references)
    store = RunStateStore(runtime.layout.framework, runtime.path_references)
    scheduler_state = SchedulerStateStore(runtime)
    log_profile = _schedule_log_profile(diagnostics, include_script=False)
    entry = ScheduleEntry(id="t0400", name="04:00", time="04:00", task_ids=["startup"])
    config = ScheduleConfig(
        id="daily",
        name="Daily",
        enabled=True,
        task_config="daily",
        profile_name="default",
        profile_data={},
        entries=[entry],
    )
    callbacks = ScheduledMaaRunCallbacks(
        runtime=runtime,
        scheduler_state=scheduler_state,
        diagnostics=diagnostics,
        config=config,
        entry=entry,
        client="Official",
        timezone_name="UTC",
        selected_task_ids=[],
        skipped_tasks=[{"task_id": "startup", "reason": "今日成功次数已满足 1/1"}],
        policies=[TaskPolicy(id="startup", name="启动", type="StartUp")],
        sorted_entries=[entry],
    )
    manager = GenericRunManager(store, diagnostics)

    state = manager.start(
        RunStartPlan(
            kind="schedule",
            title="Daily / 04:00",
            callbacks=callbacks.to_callbacks(),
            max_retries=3,
            log_profile=log_profile,
            log_files=diagnostics.stream_log_files("maa-cli", "schedule-skip"),
            event_log_file=diagnostics.event_log_file("schedule-skip"),
            initial_attempt_payload={"task_ids": []},
            history_scope=("schedules", "daily"),
        ),
        run_id="schedule-skip",
    )
    assert state.thread is not None
    state.thread.join(timeout=5)
    assert not state.thread.is_alive()

    assert state.status == "skipped"
    assert len(state.retries) == 1
    assert state.retries[0].status == "skipped"
    assert state.retries[0].closed is True
    retries = store.retries(state.id)
    assert len(retries) == 1
    assert retries[0]["status"] == "skipped"
