from __future__ import annotations

from pathlib import Path

import pytest

from maa_auto_panel.config.manager import ConfigManager
from maa_auto_panel.errors import CorruptState
from maa_auto_panel.maa.runner import load_task_file
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.scheduler.config import ScheduleConfigManager


def test_config_manager_treats_invalid_utf8_as_corrupt_state(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    manager = ConfigManager(runtime)
    path = runtime.config_dir / "tasks" / "invalid.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff")

    with pytest.raises(CorruptState, match="Cannot decode config"):
        manager.read_task_config("invalid")


def test_schedule_listing_does_not_hide_corrupt_files(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    configs = ConfigManager(runtime)
    schedules = ScheduleConfigManager(runtime, configs)
    path = runtime.schedule_config_dir / "invalid.toml"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff")

    with pytest.raises(CorruptState, match="Cannot parse schedule"):
        schedules.list_files()


@pytest.mark.parametrize(
    ("suffix", "content"),
    ((".json", b"{"), (".toml", b"key = ["), (".json", b"\xff")),
)
def test_maa_task_loader_normalizes_parse_failures(tmp_path: Path, suffix: str, content: bytes) -> None:
    path = tmp_path / f"task{suffix}"
    path.write_bytes(content)

    with pytest.raises(CorruptState, match="Cannot parse task config"):
        load_task_file(path)
