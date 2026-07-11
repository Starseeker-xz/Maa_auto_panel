from __future__ import annotations

import os
from pathlib import Path
import sys
import time

from maa_auto_panel.diagnostics import Diagnostics
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.coordinator import RunCoordinator
from maa_auto_panel.run_manager.logs import plain_stream_log_profile
from maa_auto_panel.run_manager.manager import GenericRunManager, RunCallbacks, RunStartPlan
from maa_auto_panel.run_manager.state import RunTimeouts
from maa_auto_panel.run_manager.store import RunStateStore


def test_command_run_driver_streams_logs_and_raw_lines(tmp_path: Path) -> None:
    _runtime, diagnostics, manager = _manager(tmp_path)
    raw_lines: list[tuple[str, str]] = []
    profile = plain_stream_log_profile("tool", diagnostic_sink=diagnostics.append_tool_output)
    run_id = "cmd-run"

    state = manager.start(
        RunStartPlan(
            kind="tool",
            title="Command tool",
            command=CommandSpec(
                [sys.executable, "-c", "import sys; print('hello'); print('warn', file=sys.stderr)"],
                env=os.environ.copy(),
            ),
            callbacks=RunCallbacks(on_raw_line=lambda attempt, stream, line: raw_lines.append((stream, line))),
            log_profile=profile,
            log_files=diagnostics.tool_log_files(run_id),
            event_log_file=diagnostics.event_log_file(run_id),
        ),
        run_id=run_id,
    )

    _join(state)

    assert manager.current_response()["run"]["status"] == "succeeded"  # type: ignore[index]
    assert ("stdout", "hello") in raw_lines
    assert ("stderr", "warn") in raw_lines
    assert (tmp_path / "data/debug/framework/external/tools/cmd-run.stdout.log").read_text(encoding="utf-8") == "hello\n"
    assert (tmp_path / "data/debug/framework/external/tools/cmd-run.stderr.log").read_text(encoding="utf-8") == "warn\n"


def test_command_run_driver_retries_until_command_succeeds(tmp_path: Path) -> None:
    _runtime, diagnostics, manager = _manager(tmp_path)
    counter = tmp_path / "counter.txt"
    profile = plain_stream_log_profile("tool", diagnostic_sink=diagnostics.append_tool_output)

    code = (
        "from pathlib import Path; import sys; "
        "path = Path(sys.argv[1]); "
        "count = int(path.read_text() or '0') if path.exists() else 0; "
        "path.write_text(str(count + 1)); "
        "print(f'attempt {count + 1}', flush=True); "
        "raise SystemExit(1 if count == 0 else 0)"
    )
    state = manager.start(
        RunStartPlan(
            kind="tool",
            title="Retry command",
            command=CommandSpec([sys.executable, "-c", code, str(counter)], env=os.environ.copy()),
            max_retries=2,
            log_profile=profile,
            log_files=diagnostics.tool_log_files("retry-run"),
            event_log_file=diagnostics.event_log_file("retry-run"),
        ),
        run_id="retry-run",
    )

    _join(state)

    payload = manager.current_response()
    assert payload["run"]["status"] == "succeeded"  # type: ignore[index]
    assert [retry["status"] for retry in payload["retries"]] == ["failed", "succeeded"]  # type: ignore[index]
    assert counter.read_text(encoding="utf-8") == "2"


def test_command_run_driver_stops_running_process(tmp_path: Path) -> None:
    _runtime, diagnostics, manager = _manager(tmp_path)
    profile = plain_stream_log_profile("tool", diagnostic_sink=diagnostics.append_tool_output)
    state = manager.start(
        RunStartPlan(
            kind="tool",
            title="Stop command",
            command=CommandSpec(
                [sys.executable, "-u", "-c", "import time; print('ready', flush=True); time.sleep(30)"],
                env=os.environ.copy(),
            ),
            log_profile=profile,
            timeouts=RunTimeouts(stop_kill_seconds=2),
            log_files=diagnostics.tool_log_files("stop-command"),
            event_log_file=diagnostics.event_log_file("stop-command"),
        ),
        run_id="stop-command",
    )

    assert _wait_until(lambda: state.process is not None)
    manager.stop_current()
    _join(state)

    payload = manager.current_response()
    assert payload["run"]["status"] == "stopped"  # type: ignore[index]
    assert payload["retries"][0]["status"] == "stopped"  # type: ignore[index]


def test_command_run_driver_records_runtime_timeout(tmp_path: Path) -> None:
    _runtime, diagnostics, manager = _manager(tmp_path)
    profile = plain_stream_log_profile("tool", diagnostic_sink=diagnostics.append_tool_output)
    state = manager.start(
        RunStartPlan(
            kind="tool",
            title="Timeout command",
            command=CommandSpec([sys.executable, "-c", "import time; time.sleep(30)"], env=os.environ.copy()),
            log_profile=profile,
            timeouts=RunTimeouts(runtime_kill_seconds=1),
            log_files=diagnostics.tool_log_files("timeout-command"),
            event_log_file=diagnostics.event_log_file("timeout-command"),
        ),
        run_id="timeout-command",
    )

    _join(state, timeout=4)

    payload = manager.current_response()
    assert payload["run"]["status"] == "failed"  # type: ignore[index]
    assert any("运行时间已超过上限" in str(event.get("text")) for event in diagnostics.run_events("timeout-command"))


def _manager(tmp_path: Path) -> tuple[MaaRuntime, Diagnostics, GenericRunManager]:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime)
    return runtime, diagnostics, GenericRunManager(runtime, RunStateStore(runtime), diagnostics, RunCoordinator())


def _join(state, *, timeout: float = 3) -> None:
    assert state.thread is not None
    state.thread.join(timeout=timeout)
    assert not state.thread.is_alive()


def _wait_until(predicate, *, timeout: float = 2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False
