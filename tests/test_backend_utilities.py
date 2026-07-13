from pathlib import Path
import asyncio
import os
import sys

import pytest

from maa_auto_panel.config.app_settings import FrameworkSettingsManager
from maa_auto_panel.config.manager import ConfigManager
from maa_auto_panel.diagnostics import Diagnostics
from maa_auto_panel.errors import Conflict
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.process import run_streaming_process
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.contracts import RunScriptHooks, RunScriptSpec, RunStartPlan, RunTextTemplates
from maa_auto_panel.run_manager.coordinator import RunCoordinator
from maa_auto_panel.run_manager.manager import GenericRunManager
from maa_auto_panel.run_manager.state import LiveRun, RunTimeouts
from maa_auto_panel.run_manager.store import RunStateStore
from maa_auto_panel.scheduler.models import RestartScriptPolicy, ScheduleConfig, ScheduleEntry
from maa_auto_panel.scheduler.scripts import ScheduleScriptManager
from maa_auto_panel.scheduler.service import SchedulerService, _schedule_log_profile, _schedule_script_log_profile
from maa_auto_panel.tools.manager import ToolRunManager, _build_game_update_command
from maa_auto_panel.utils import is_newer_version, write_text_atomic
from maa_auto_panel.web.app import create_app


def test_config_resolve_rejects_path_traversal(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    manager = ConfigManager(runtime)
    (runtime.config_dir / "tasks").mkdir(parents=True)
    (runtime.config_dir / "tasks" / "daily.toml").write_text('tasks = []\n', encoding="utf-8")

    assert manager.resolve("tasks", "daily").name == "daily.toml"
    with pytest.raises(ValueError):
        manager.resolve("tasks", "../daily")


def test_write_text_atomic_replaces_content(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    write_text_atomic(path, "first")
    write_text_atomic(path, "second")

    assert path.read_text(encoding="utf-8") == "second"
    assert not list(tmp_path.glob(".*.tmp"))


def test_version_compare_accepts_v_prefix_and_suffix() -> None:
    assert is_newer_version("v6.13.0", "6.14.0")
    assert not is_newer_version("6.14.0", "v6.13.0")
    assert not is_newer_version("v0.7.5", "0.7.5")


def test_streaming_process_preserves_carriage_returns_for_log_translator(tmp_path: Path) -> None:
    chunks: list[str] = []

    result = run_streaming_process(
        [
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('first\\rsecond\\n'); sys.stderr.flush()",
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
        on_output=lambda text: None,
        on_stream_output=lambda stream, text: chunks.append(text),
    )

    assert result.return_code == 0
    assert "first\r" in chunks
    assert "second\n" in chunks


def test_game_update_tool_runs_python_unbuffered(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    manager = ToolRunManager(
        runtime,
        ConfigManager(runtime),
        RunStateStore(runtime.layout.framework, runtime.path_references),
        Diagnostics(runtime.layout.framework, runtime.path_references),
        FrameworkSettingsManager(runtime),
        RunCoordinator(),
    )

    command = _build_game_update_command(manager, {"address": "127.0.0.1:5555"})

    assert command.cmd[:4] == [sys.executable, "-u", "-m", "maa_auto_panel.tools.game"]
    assert command.cmd[4] == "update-game"


def test_tool_start_rejects_stopping_current_run(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    manager = ToolRunManager(
        runtime,
        ConfigManager(runtime),
        RunStateStore(runtime.layout.framework, runtime.path_references),
        Diagnostics(runtime.layout.framework, runtime.path_references),
        FrameworkSettingsManager(runtime),
        RunCoordinator(),
    )
    state = LiveRun(
        id="run-1",
        kind="tool",
        title="更新游戏",
        status="stopping",
        started_at="2026-07-03T00:00:00",
        updated_at="2026-07-03T00:00:00",
        metadata={"tool_id": "game-update", "tool_title": "更新游戏"},
    )
    with manager.runs._lock:
        manager.runs._runs[state.id] = state
        manager.runs._current_run_id = state.id

    with pytest.raises(Conflict):
        manager.start("game-update", {})


def test_live_run_retry_count_and_terminal_force_stop_are_stable() -> None:
    state = LiveRun(
        id="run-1",
        kind="schedule",
        title="Daily / 19:00",
        status="stopped",
        started_at="2026-07-05T18:00:00",
        updated_at="2026-07-05T18:24:02",
        metadata={"retry_count": 12},
    )
    state.begin_retry()

    state.request_force_stop()
    data = state.run_dict()

    assert data["status"] == "stopped"
    assert data["retry_count"] == 1
    assert data["force_stop_requested"] is False


def test_scheduler_force_stop_terminal_current_run_is_idempotent() -> None:
    service = SchedulerService.__new__(SchedulerService)
    state = LiveRun(
        id="run-1",
        kind="schedule",
        title="Daily / 19:00",
        status="stopped",
        started_at="2026-07-05T18:00:00",
        updated_at="2026-07-05T18:24:02",
        metadata={"schedule_id": "daily"},
    )

    class FakeRuns:
        def force_stop_current(self) -> LiveRun:
            return state

    service.runs = FakeRuns()

    returned = service.force_stop_current()

    assert returned is state
    assert state.status == "stopped"
    assert state.force_stop_requested is False


def test_create_schedule_keeps_explicit_task_config_when_listing_is_empty() -> None:
    service = SchedulerService.__new__(SchedulerService)

    class EmptyConfigs:
        schema_validator = None

        def list_kind(self, kind: str) -> list[object]:
            assert kind == "tasks"
            return []

        def read_task_config(self, name: str) -> dict[str, object]:
            assert name == "custom-task"
            return {"task_items": [{"id": "startup"}]}

        def read_profile_config(self, name: str) -> dict[str, object]:
            assert name == "default"
            return {"data": {}}

    class FakeSchedules:
        def create_default(
            self,
            *,
            name: str,
            task_config: str,
            default_profile: dict[str, object],
            task_ids: list[str],
        ) -> ScheduleConfig:
            assert task_config == "custom-task"
            assert task_ids == ["startup"]
            return ScheduleConfig(
                id="custom-schedule",
                name=name,
                enabled=False,
                task_config=task_config,
                profile_name="custom-profile",
                profile_data=default_profile,
            )

    service.configs = EmptyConfigs()
    service.schedules = FakeSchedules()
    service._schedule_response = lambda config: {"config": config.to_dict()}

    response = service.create_schedule("custom schedule", task_config="custom-task")

    assert response["config"]["task_config"] == "custom-task"


def test_schedule_response_uses_single_current_snapshot_for_matching_run() -> None:
    service = SchedulerService.__new__(SchedulerService)
    run = LiveRun(
        id="run-1",
        kind="schedule",
        title="Target schedule / 04:00",
        status="running",
        started_at="2026-07-01T04:00:00",
        updated_at="2026-07-01T04:00:00",
        metadata={
            "schedule_id": "target-schedule",
            "schedule_name": "Target schedule",
            "entry_id": "t0400",
            "entry_name": "04:00",
            "task_config": "daily",
            "profile": "default",
            "profile_name": "default",
            "log_level": 1,
            "game_day": "2026-07-01",
            "trigger": "manual",
        },
    )
    calls = 0

    def current() -> LiveRun | None:
        nonlocal calls
        calls += 1
        return run if calls == 1 else None

    class FakeConfigs:
        def read_task_config(self, name: str) -> dict[str, object]:
            assert name == "daily"
            return {"data": {}, "task_items": []}

    class FakeSettings:
        def read(self) -> dict[str, object]:
            return {"effective_timezone": {"name": "UTC"}}

    class FakeSchedulerState:
        def daily_stats(self, schedule_id: str, game_day: str) -> dict[str, object]:
            assert schedule_id == "target-schedule"
            assert game_day
            return {}

    class FakeRunStore:
        def runs(self, kind: str | None = None, *, limit: int = 50) -> list[object]:
            assert kind == "schedule"
            return []

    class FakeFileInfo:
        def to_dict(self) -> dict[str, object]:
            return {"filename": "target-schedule.toml", "path": "config/framework/schedules/target-schedule.toml"}

    class FakeSchedules:
        def file_info(self, config: ScheduleConfig) -> FakeFileInfo:
            assert config.id == "target-schedule"
            return FakeFileInfo()

    class FakeScripts:
        def list_scripts(self) -> list[object]:
            return []

    def current_response(schedule_id: str | None = None, *, include_logs: bool = True) -> dict[str, object]:
        snapshot = current()
        if snapshot is None or schedule_id != "target-schedule":
            return {"status": "idle", "output": []}
        return snapshot.to_dict(include_logs=include_logs)

    service.current = current  # type: ignore[method-assign]
    service.current_response = current_response  # type: ignore[method-assign]
    service.configs = FakeConfigs()
    service.framework_settings = FakeSettings()
    service.schedules = FakeSchedules()
    service.store = FakeRunStore()
    service.scheduler_state = FakeSchedulerState()
    service.scripts = FakeScripts()
    config = ScheduleConfig(
        id="target-schedule",
        name="Target schedule",
        enabled=True,
        task_config="daily",
        profile_name="default",
        profile_data={},
        entries=[ScheduleEntry(id="t0400", name="04:00", time="04:00", task_ids=[])],
    )

    response = service._schedule_response(config)

    assert calls == 1
    assert response["current_run"]["run"]["id"] == "run-1"


def test_schedule_restart_script_streams_to_visible_logs_and_diagnostics(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime.layout.framework, runtime.path_references)
    store = RunStateStore(runtime.layout.framework, runtime.path_references)
    script_path = runtime.script_dir / "hook.sh"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        "# framework-var: TARGET | Target | default\n"
        "printf 'Summary\\n'\n"
        "printf 'target=%s\\n' \"$TARGET\"\n"
        "printf 'warn=%s\\n' \"$MAA_CONFIG_DIR\" >&2\n",
        encoding="utf-8",
    )
    config = ScheduleConfig(
        id="daily",
        name="Daily",
        enabled=True,
        task_config="daily",
        profile_name="default",
        profile_data={},
        restart=RestartScriptPolicy(mode="before_run", script="hook.sh", variables={"TARGET": "ark"}),
    )
    log_profile = _schedule_log_profile(diagnostics, include_script=True)
    script_manager = ScheduleScriptManager(runtime)
    script_log_profile = _schedule_script_log_profile(diagnostics)

    def script_command(_attempt) -> CommandSpec:
        command = script_manager.command(config.restart.script, config.restart.variables)
        return CommandSpec(command.cmd, cwd=tmp_path, env=command.env)

    manager = GenericRunManager(store, diagnostics)
    state = manager.start(
        RunStartPlan(
            kind="schedule",
            title="Daily / 04:00",
            command=CommandSpec([sys.executable, "-c", ""], cwd=tmp_path, env=os.environ.copy()),
            log_profile=log_profile,
            script_hooks=RunScriptHooks(
                before_run=(
                    RunScriptSpec(
                        command=script_command,
                        label="hook.sh",
                        source_prefix="script",
                        timeouts=RunTimeouts(runtime_kill_seconds=120),
                        log_profile=script_log_profile,
                    ),
                )
            ),
            script_log_profile=script_log_profile,
            log_files={**diagnostics.stream_log_files("maa-cli", "run-script"), **diagnostics.stream_log_files("scripts", "run-script", key_prefix="script_")},
            event_log_file=diagnostics.event_log_file("run-script"),
            text=RunTextTemplates(start="", completed="", exit_code=""),
        ),
        run_id="run-script",
    )
    assert state.thread is not None
    state.thread.join(timeout=5)
    assert not state.thread.is_alive()

    entries = state.to_dict()["retries"][0]["log_entries"]
    lines = [entry["messages"][0]["text"] for entry in entries if entry["kind"] in {"event", "line"}]
    assert lines[0] == "运行脚本(before_run): hook.sh"
    assert set(lines[1:]) == {"Summary", "target=ark", f"warn={runtime.config_dir}"}
    assert state.retries[0].metadata == {}
    assert (tmp_path / "data/debug/framework/external/scripts/run-script.stdout.log").read_text(encoding="utf-8") == "Summary\ntarget=ark\n"
    assert (tmp_path / "data/debug/framework/external/scripts/run-script.stderr.log").read_text(encoding="utf-8") == f"warn={runtime.config_dir}\n"


def test_create_app_exposes_expected_api_paths(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    paths = set(app.openapi()["paths"])

    assert "/api/configs" in paths
    assert "/api/settings" in paths
    assert "/api/maintenance/current" in paths
    assert "/api/tools/current" in paths
    assert "/api/history/runs" in paths
    assert "/api/maa/stages" in paths
    assert "/api/schedules/current" in paths
    assert "/api/runs/current" in paths


def test_api_requests_are_written_to_framework_log(tmp_path: Path) -> None:
    app = create_app(tmp_path)

    status = asyncio.run(_asgi_get_status(app, "/api/history/runs"))

    assert status == 200
    framework_log = tmp_path / "data/debug/framework/framework.log"
    content = framework_log.read_text(encoding="utf-8")
    assert "INFO" in content
    assert "api request started method=GET path=/api/history/runs" in content
    assert "api request finished method=GET path=/api/history/runs status=200" in content


async def _asgi_get_status(app, path: str) -> int:
    messages: list[dict[str, object]] = []
    received = False

    async def receive() -> dict[str, object]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )
    for message in messages:
        if message.get("type") == "http.response.start":
            return int(message["status"])
    raise AssertionError("ASGI response did not start")
