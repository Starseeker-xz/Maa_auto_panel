from pathlib import Path

from linux_maa.config.manager import ConfigManager
from linux_maa.config.schema import ConfigSchemaValidator
from linux_maa.config.tasks import task_items_to_config_data
from linux_maa.maa.runtime import MaaRuntime


def repo_runtime() -> MaaRuntime:
    return MaaRuntime(Path(__file__).resolve().parents[1])


def test_retry_even_success_metadata_is_valid() -> None:
    data = {
        "$schema": "../../../docs/maa-cli/schemas/task.schema.json",
        "tasks": [
            {
                "name": "启动 B 服",
                "type": "StartUp",
                "params": {"client_type": "Bilibili", "start_game_enabled": True},
                "linux_maa": {
                    "id": "startup",
                    "unlimited_runs": True,
                    "important": True,
                    "retry_even_success": True,
                },
            }
        ],
    }

    result = ConfigSchemaValidator(repo_runtime()).validate_task_config(data)

    assert result.valid


def test_retry_even_success_round_trips_through_task_items() -> None:
    manager = ConfigManager(repo_runtime())
    data = {
        "$schema": "../../../docs/maa-cli/schemas/task.schema.json",
        "tasks": [
            {
                "name": "关闭游戏",
                "type": "CloseDown",
                "params": {"client_type": "Bilibili"},
                "linux_maa": {
                    "id": "closedown",
                    "unlimited_runs": True,
                    "important": True,
                    "retry_even_success": True,
                },
            }
        ],
    }

    items = manager.task_items_from_data(data)
    written = task_items_to_config_data({"$schema": data["$schema"]}, items)

    assert items[0]["linux_maa"]["retry_even_success"] is True
    assert written["tasks"][0]["linux_maa"]["retry_even_success"] is True
