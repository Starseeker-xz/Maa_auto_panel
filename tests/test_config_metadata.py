from pathlib import Path

from maa_auto_panel.config.manager import ConfigManager
from maa_auto_panel.config.schema import ConfigSchemaValidator
from maa_auto_panel.config.tasks import prepare_framework_task_config, task_items_to_config_data
from maa_auto_panel.maa.runtime import MaaRuntime


def repo_runtime() -> MaaRuntime:
    repo_root = Path(__file__).resolve().parents[1]
    return MaaRuntime(repo_root)


def test_retry_even_success_metadata_is_valid() -> None:
    data = {
        "$schema": "../../../docs/maa-cli/schemas/task.schema.json",
        "tasks": [
            {
                "name": "启动 B 服",
                "type": "StartUp",
                "params": {"client_type": "Bilibili", "start_game_enabled": True},
                "framework": {
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
                "framework": {
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

    assert items[0]["framework"]["retry_even_success"] is True
    assert written["tasks"][0]["framework"]["retry_even_success"] is True


def test_txwy_client_type_matches_current_integration_docs() -> None:
    data = {
        "$schema": "../../../docs/maa-cli/schemas/task.schema.json",
        "tasks": [
            {
                "name": "启动腾讯服",
                "type": "StartUp",
                "params": {"client_type": "txwy", "start_game_enabled": True},
            }
        ],
    }

    result = ConfigSchemaValidator(repo_runtime()).validate_task_config(data)

    assert result.valid


def test_infrast_runtime_preprocess_logs_plan_name() -> None:
    messages: list[str] = []
    data = {
        "$schema": "../../../docs/maa-cli/schemas/task.schema.json",
        "tasks": [
            {
                "name": "基建",
                "type": "Infrast",
                "params": {
                    "mode": 10000,
                    "filename": "排班.json",
                    "plan_index": "__framework_runtime__:infrast_plan_index",
                },
                "framework": {
                    "managed_params": {
                        "plan_index": {
                            "type": "runtime",
                            "handler": "infrast_plan_index",
                            "value": "2",
                        }
                    }
                },
            }
        ],
    }

    prepare_framework_task_config(data, repo_runtime(), messages)

    assert "选择基建计划: 排班.json / 常态班" in messages
