from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import threading
import time

import pytest
from maa_auto_panel.diagnostics import Diagnostics
from maa_auto_panel.errors import RuntimeUnavailable
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.contracts import RunStartPlan
from maa_auto_panel.run_manager.coordinator import RunCoordinator, RunLease
from maa_auto_panel.run_manager.logs import plain_stream_log_profile
from maa_auto_panel.run_manager.manager import GenericRunManager
from maa_auto_panel.run_manager.store import RunStateStore
from maa_auto_panel.run_resources import adb_device_resource
from maa_auto_panel.web.app import create_app
from maa_auto_panel.web.services import _join_managers_until, create_services


def test_app_lifespan_starts_and_joins_scheduler(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    services = app.state.services

    assert services.scheduler._thread is None
    asyncio.run(_exercise_lifespan(app))

    assert services.scheduler._thread is not None
    assert not services.scheduler._thread.is_alive()
    services.close(normal_timeout=0, force_timeout=0)


async def _exercise_lifespan(app) -> None:
    async with app.router.lifespan_context(app):
        services = app.state.services
        assert services.scheduler._thread is not None
        assert services.scheduler._thread.is_alive()


def test_manager_rejects_new_runs_after_shutdown_begins(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    manager = GenericRunManager(RunStateStore(runtime.layout.data, runtime.path_references), Diagnostics(runtime.layout.data, runtime.path_references))
    manager.begin_shutdown()

    with pytest.raises(RuntimeUnavailable, match="shutting down"):
        manager.start(
            RunStartPlan(
                kind="tool",
                title="late run",
                command=CommandSpec([sys.executable, "-c", "pass"], cwd=tmp_path, env=os.environ.copy()),
            )
        )


def test_coordinator_shutdown_wakes_waiting_acquire() -> None:
    coordinator = RunCoordinator()
    resource = adb_device_resource("127.0.0.1:5555")
    assert resource is not None
    coordinator.acquire(RunLease("active", "test", "active", 10, resources=(resource,)))
    finished = threading.Event()
    errors: list[Exception] = []

    def wait_for_resource() -> None:
        try:
            coordinator.acquire(RunLease("waiting", "test", "waiting", 10, resources=(resource,)))
        except Exception as exc:
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=wait_for_resource)
    thread.start()
    assert not finished.wait(0.05)

    coordinator.begin_shutdown()

    assert finished.wait(1)
    thread.join(timeout=1)
    assert len(errors) == 1
    assert "shutting down" in str(errors[0])


def test_shared_join_deadline_does_not_accumulate_per_manager() -> None:
    deadlines: list[float] = []

    class SlowManager:
        def join_until(self, deadline: float) -> bool:
            deadlines.append(deadline)
            time.sleep(max(0.0, deadline - time.monotonic()))
            return False

    managers = (SlowManager(), SlowManager(), SlowManager(), SlowManager())
    started = time.monotonic()
    deadline = started + 0.05

    remaining = _join_managers_until(managers, deadline)

    assert len(remaining) == 4
    assert len(set(deadlines)) == 1
    assert time.monotonic() - started < 0.15


def test_web_services_close_stops_all_run_managers_with_shared_budget(tmp_path: Path) -> None:
    services = create_services(tmp_path)
    services.start()
    states = []
    for index, manager in enumerate(services._run_managers(), start=1):
        states.append(
            manager.start(
                RunStartPlan(
                    kind="tool",
                    title=f"shutdown-{index}",
                    command=CommandSpec(
                        [sys.executable, "-u", "-c", "import time; print('ready', flush=True); time.sleep(30)"],
                        cwd=tmp_path,
                        env=os.environ.copy(),
                    ),
                ),
                run_id=f"shutdown-{index}",
            )
        )
    assert _wait_until(lambda: all(state.process is not None for state in states))

    started = time.monotonic()
    services.close(normal_timeout=2, force_timeout=1)

    assert time.monotonic() - started < 3
    assert all(state.status == "stopped" for state in states)
    assert all(state.thread is not None and not state.thread.is_alive() for state in states)
    assert services.scheduler._thread is not None
    assert not services.scheduler._thread.is_alive()


def test_force_stop_kills_process_group_descendants(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime.layout.data, runtime.path_references)
    manager = GenericRunManager(RunStateStore(runtime.layout.data, runtime.path_references), diagnostics)
    pid_file = tmp_path / "child.pid"
    child_code = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"
    parent_code = (
        "import pathlib,signal,subprocess,sys,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "child=subprocess.Popen([sys.executable,'-c',sys.argv[2]]); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); "
        "print('ready', flush=True); time.sleep(30)"
    )
    state = manager.start(
        RunStartPlan(
            kind="tool",
            title="process tree",
            command=CommandSpec(
                [sys.executable, "-u", "-c", parent_code, str(pid_file), child_code],
                cwd=tmp_path,
                env=os.environ.copy(),
            ),
            log_profile=plain_stream_log_profile("tool", diagnostic_sink=diagnostics.stream_sink(("tools", "generic"))),
        ),
        run_id="process-tree",
    )
    assert _wait_until(lambda: pid_file.exists() and state.process is not None)
    child_pid = int(pid_file.read_text(encoding="utf-8"))

    manager.force_stop_current()

    assert state.thread is not None
    state.thread.join(timeout=3)
    assert not state.thread.is_alive()
    assert state.status == "stopped"
    assert _wait_until(lambda: not _process_is_running(child_pid), timeout=3)


def _wait_until(predicate, *, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def _process_is_running(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    if not stat.exists():
        return False
    fields = stat.read_text(encoding="utf-8", errors="replace").split()
    return len(fields) > 2 and fields[2] != "Z"
