from __future__ import annotations

import os
import sys
import time

from linux_maa.diagnostics import Diagnostics
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.run_manager.command import CommandSpec
from linux_maa.run_manager.coordinator import RunCoordinator
from linux_maa.run_manager.manager import GenericRunManager, RetryDecision, RunAttempt, RunCallbacks, RunStartPlan
from linux_maa.run_manager.state import RunTimeouts
from linux_maa.run_manager.store import RunStateStore
from linux_maa.run_resources import RunResource


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


def _wait_until(predicate, *, timeout: float = 2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False
