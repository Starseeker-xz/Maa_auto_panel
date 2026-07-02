from pathlib import Path
import asyncio

import pytest

from linux_maa.config.manager import ConfigManager
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.scheduler.models import ScheduleConfig, ScheduleEntry
from linux_maa.scheduler.service import SchedulerService, ScheduleRunState
from linux_maa.utils import is_newer_version, write_text_atomic
from linux_maa.web.app import create_app


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
    run = ScheduleRunState(
        id="run-1",
        schedule_id="target-schedule",
        schedule_name="Target schedule",
        entry_id="t0400",
        entry_name="04:00",
        task_config="daily",
        profile_name="default",
        status="running",
        created_at="2026-07-01T04:00:00",
        updated_at="2026-07-01T04:00:00",
        log_level=1,
        game_day="2026-07-01",
        trigger="manual",
    )
    calls = 0

    def current() -> ScheduleRunState | None:
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

    class FakeStore:
        def daily_stats(self, schedule_id: str, game_day: str) -> dict[str, object]:
            assert schedule_id == "target-schedule"
            assert game_day
            return {}

        def recent_runs(self, schedule_id: str, *, limit: int) -> list[object]:
            assert schedule_id == "target-schedule"
            assert limit == 12
            return []

    class FakeFileInfo:
        def to_dict(self) -> dict[str, object]:
            return {"filename": "target-schedule.toml", "path": "config/linux-maa/schedules/target-schedule.toml"}

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
    service.store = FakeStore()
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
    assert response["current_run"]["id"] == "run-1"


def test_create_app_exposes_expected_api_paths(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    paths = set(app.openapi()["paths"])

    assert "/api/configs" in paths
    assert "/api/settings" in paths
    assert "/api/maintenance/current" in paths
    assert "/api/history/runs" in paths
    assert "/api/maa/stages" in paths
    assert "/api/schedules/current" in paths
    assert "/api/runs/current" in paths


def test_api_requests_are_written_to_framework_log(tmp_path: Path) -> None:
    app = create_app(tmp_path)

    status = asyncio.run(_asgi_get_status(app, "/api/history/runs"))

    assert status == 200
    framework_log = tmp_path / "debug/linux-maa/framework.log"
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
