from __future__ import annotations

import gc
import os
import sys
import time
import weakref

from maa_auto_panel.diagnostics import Diagnostics
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.coordinator import RunCoordinator, RunLease
from maa_auto_panel.run_manager.manager import GenericRunManager, RetryDecision, RunAttempt, RunCallbacks, RunStartPlan
from maa_auto_panel.run_manager.state import RunTimeouts
from maa_auto_panel.run_manager.store import RunStateStore
from maa_auto_panel.run_resources import RunResource


def test_generic_run_manager_persists_retry_and_releases_resources(tmp_path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime)
    store = RunStateStore(runtime)
    coordinator = RunCoordinator()
    manager = GenericRunManager(runtime, store, diagnostics, coordinator)
    seen_payloads: list[dict[str, object]] = []

    def on_start(attempt: RunAttempt) -> None:
        assert attempt.payload == {"task_ids": ["task-1"]}
        attempt.add_event("开始通用运行")

    def evaluate(attempt: RunAttempt, _result) -> RetryDecision:
        seen_payloads.append(attempt.payload)
        if attempt.attempt_index == 1:
            return RetryDecision(
                "failed",
                1,
                continue_retry=True,
                next_attempt_payload={"task_ids": ["task-2"]},
                retry_metadata={"task_ids": attempt.payload["task_ids"], "task_results": [{"task_id": "task-1", "status": "failed"}]},
                retry_artifacts={"generated_config_dir": "runtime/generated/run-1"},
            )
        return RetryDecision(
            "succeeded",
            0,
            run_status="succeeded",
            retry_metadata={"task_ids": attempt.payload["task_ids"], "task_results": [{"task_id": "task-2", "status": "succeeded"}]},
            retry_artifacts={"generated_config_dir": "runtime/generated/run-2"},
            summary_patch={"done": True},
        )

    state = manager.start(
        RunStartPlan(
            kind="tool",
            title="Generic tool",
            command=CommandSpec([sys.executable, "-c", "print('raw output')"], env=os.environ.copy()),
            callbacks=RunCallbacks(on_start=on_start, evaluate_attempt=evaluate),
            max_retries=2,
            event_log_file=diagnostics.event_log_file("run-1"),
            initial_attempt_payload={"task_ids": ["task-1"]},
            history_scope=("tools", "generic"),
            resources=(RunResource("device", "serial-1"),),
        ),
        run_id="run-1",
    )

    assert state.thread is not None
    state.thread.join(timeout=2)
    assert not state.thread.is_alive()

    payload = manager.current_response()
    assert payload["run"]["status"] == "succeeded"  # type: ignore[index]
    assert seen_payloads == [{"task_ids": ["task-1"]}, {"task_ids": ["task-2"]}]
    assert payload["retries"][0]["status"] == "failed"  # type: ignore[index]
    assert payload["retries"][1]["status"] == "succeeded"  # type: ignore[index]
    assert payload["retries"][1]["closed"] is True  # type: ignore[index]
    assert "task_ids" not in payload["retries"][0]  # type: ignore[operator]
    assert "generated_config_dir" not in payload["retries"][0]  # type: ignore[operator]
    assert payload["stream_version"] > 0
    assert coordinator.occupied_resources() == []

    stored = store.run("run-1")
    assert stored is not None
    assert stored.status == "succeeded"
    assert stored.retry_count == 2
    assert stored.metadata["summary"] == {"done": True}
    assert stored.history_scope == ("tools", "generic")
    retries = store.retries("run-1")
    assert retries[0]["metadata"]["task_results"] == [{"task_id": "task-1", "status": "failed"}]
    assert retries[0]["artifacts"]["generated_config_dir"] == "runtime/generated/run-1"
    assert retries[1]["metadata"]["task_results"] == [{"task_id": "task-2", "status": "succeeded"}]
    assert retries[1]["artifacts"]["generated_config_dir"] == "runtime/generated/run-2"


def test_generic_run_manager_stop_current_adds_event_and_does_not_prepare_next_retry(tmp_path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime)
    manager = GenericRunManager(runtime, RunStateStore(runtime), diagnostics, RunCoordinator())

    state = manager.start(
        RunStartPlan(
            kind="maintenance",
            title="Generic maintenance",
            command=CommandSpec(
                [sys.executable, "-u", "-c", "import time; print('ready', flush=True); time.sleep(30)"],
                env=os.environ.copy(),
            ),
            max_retries=2,
            timeouts=RunTimeouts(stop_kill_seconds=2),
            event_log_file=diagnostics.event_log_file("stop-run"),
        ),
        run_id="stop-run",
    )

    assert _wait_until(lambda: state.process is not None)
    stopped = manager.stop_current()
    assert stopped.status == "stopping"
    assert state.thread is not None
    state.thread.join(timeout=5)
    assert not state.thread.is_alive()

    payload = manager.current_response()
    assert payload["run"]["status"] == "stopped"  # type: ignore[index]
    assert len(payload["retries"]) == 1  # type: ignore[arg-type]
    assert payload["retries"][0]["status"] == "stopped"  # type: ignore[index]
    events = diagnostics.run_events("stop-run")
    texts = [str(event.get("text")) for event in events]
    assert any("收到停止请求" in text for text in texts)
    assert not any("第 2 次重试" in text or "准备重试" in text for text in texts)


def test_equal_priority_resource_wait_is_visible_before_command_starts(tmp_path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime)
    coordinator = RunCoordinator()
    resource = RunResource("device", "serial-1")
    coordinator.acquire(RunLease("blocker", "tool", "现有运行", 10, resources=(resource,)))
    marker = tmp_path / "started"
    manager = GenericRunManager(runtime, RunStateStore(runtime), diagnostics, coordinator)

    def on_start(attempt: RunAttempt) -> None:
        attempt.add_event("运行前操作完成")

    state = manager.start(
        RunStartPlan(
            kind="tool",
            title="Waiting tool",
            command=CommandSpec([sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"], env=os.environ.copy()),
            callbacks=RunCallbacks(on_start=on_start),
            resources=(resource,),
        ),
        run_id="waiting-run",
    )

    try:
        assert _wait_until(lambda: _retry_has_text(state, "等待运行资源释放"))
        assert _retry_has_text(state, "运行前操作完成")
        assert not marker.exists()
        stored_waiting = manager.store.run(state.id)
        assert stored_waiting is not None
        assert stored_waiting.status == "running"
        assert stored_waiting.metadata["resource_wait"]["status"] == "waiting"
    finally:
        coordinator.release("blocker")
    assert state.thread is not None
    state.thread.join(timeout=2)
    assert marker.exists()
    assert state.status == "succeeded"
    assert manager.store.run(state.id).metadata["resource_wait"]["status"] == "acquired"


def test_resource_wait_timeout_fails_complete_run_without_starting_command(tmp_path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime)
    coordinator = RunCoordinator()
    resource = RunResource("device", "serial-1")
    coordinator.acquire(RunLease("blocker", "tool", "现有运行", 10, resources=(resource,)))
    marker = tmp_path / "should-not-start"
    manager = GenericRunManager(
        runtime,
        RunStateStore(runtime),
        diagnostics,
        coordinator,
        resource_wait_timeout_seconds=lambda: 0.05,
    )

    state = manager.start(
        RunStartPlan(
            kind="tool",
            title="Timed out tool",
            command=CommandSpec([sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"], env=os.environ.copy()),
            max_retries=3,
            resources=(resource,),
        ),
        run_id="resource-timeout",
    )
    assert state.thread is not None
    state.thread.join(timeout=2)

    assert not marker.exists()
    assert state.status == "failed"
    assert len(state.retries) == 1
    assert _retry_has_text(state, "等待运行资源超过全局上限")
    stored = manager.store.run(state.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.retry_count == 1
    coordinator.release("blocker")


def test_stopping_resource_wait_finishes_without_starting_command(tmp_path) -> None:
    runtime = MaaRuntime(tmp_path)
    coordinator = RunCoordinator()
    resource = RunResource("device", "serial-1")
    coordinator.acquire(RunLease("blocker", "tool", "现有运行", 10, resources=(resource,)))
    marker = tmp_path / "stopped-before-start"
    manager = GenericRunManager(runtime, RunStateStore(runtime), Diagnostics(runtime), coordinator)
    state = manager.start(
        RunStartPlan(
            kind="tool",
            title="Stopped waiter",
            command=CommandSpec([sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"], env=os.environ.copy()),
            resources=(resource,),
        ),
        run_id="stopped-waiter",
    )

    try:
        assert _wait_until(lambda: _retry_has_text(state, "等待运行资源释放"))
        manager.stop(state.id)
        assert state.thread is not None
        state.thread.join(timeout=1)
        assert not state.thread.is_alive()
        assert state.status == "stopped"
        assert not marker.exists()
    finally:
        coordinator.release("blocker")


def test_terminal_run_releases_plan_callbacks_and_bounds_live_state(tmp_path) -> None:
    runtime = MaaRuntime(tmp_path)
    manager = GenericRunManager(runtime, RunStateStore(runtime), Diagnostics(runtime), RunCoordinator())

    class CallbackOwner:
        def on_start(self, _attempt: RunAttempt) -> None:
            return None

    owner = CallbackOwner()
    owner_ref = weakref.ref(owner)
    plan = RunStartPlan(
        kind="tool",
        title="first",
        command=CommandSpec([sys.executable, "-c", "pass"], env=os.environ.copy()),
        callbacks=RunCallbacks(on_start=owner.on_start),
    )
    first = manager.start(plan, run_id="first")
    assert first.thread is not None
    first.thread.join(timeout=2)
    assert first.status == "succeeded"
    assert "first" not in manager._plans

    del plan
    del owner
    gc.collect()
    assert owner_ref() is None

    second = manager.start(
        RunStartPlan(
            kind="tool",
            title="second",
            command=CommandSpec([sys.executable, "-c", "pass"], env=os.environ.copy()),
        ),
        run_id="second",
    )
    assert second.thread is not None
    second.thread.join(timeout=2)
    assert set(manager._runs) == {"second"}
    assert manager.current_response()["run"]["id"] == "second"  # type: ignore[index]


def _wait_until(predicate, *, timeout: float = 2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _retry_has_text(state, expected: str) -> bool:
    if not state.retries:
        return False
    for entry in state.retries[0].log.entries():
        if expected in str(entry.get("title")):
            return True
        messages = entry.get("messages")
        if isinstance(messages, list) and any(expected in str(message.get("text")) for message in messages if isinstance(message, dict)):
            return True
    return False
