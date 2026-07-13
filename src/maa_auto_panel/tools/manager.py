from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from maa_auto_panel.config.app_settings import FrameworkSettingsManager
from maa_auto_panel.config.manager import ConfigManager
from maa_auto_panel.diagnostics import Diagnostics, get_logger
from maa_auto_panel.errors import InvalidRequest
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.contracts import RunStartPlan, RunTextTemplates
from maa_auto_panel.run_manager.coordinator import RunCoordinator
from maa_auto_panel.run_manager.logs import plain_stream_log_profile
from maa_auto_panel.run_manager.manager import GenericRunManager
from maa_auto_panel.run_manager.state import LiveRun
from maa_auto_panel.run_manager.store import RunStateStore
from maa_auto_panel.run_resources import RUN_PRIORITY_NORMAL, RunResource, adb_device_resource
from maa_auto_panel.settings import DEFAULT_DEVICE_SERIAL
from maa_auto_panel.utils import dict_value


logger = get_logger(__name__)


@dataclass(frozen=True)
class ToolField:
    """Describes a single input field for a tool config form."""
    id: str
    label: str
    kind: str = "text"
    required: bool = True
    placeholder: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "required": self.required,
            "placeholder": self.placeholder,
        }


@dataclass(frozen=True)
class ToolDefinition:
    """Metadata for a registered tool: id, title, description, and input fields."""
    id: str
    title: str
    description: str
    fields: tuple[ToolField, ...] = ()

    def to_dict(self, *, default_config: dict[str, object] | None = None) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "fields": [field.to_dict() for field in self.fields],
            "default_config": default_config or {},
        }


@dataclass(frozen=True)
class ToolCommand:
    """Holds shell command (argv list) and environment variables for executing a tool process."""
    cmd: list[str]
    env: dict[str, str]


ToolCommandBuilder = Callable[["ToolRunManager", dict[str, object]], ToolCommand]


@dataclass(frozen=True)
class ToolSpec:
    """Binds a ToolDefinition to its command-builder, forming a complete tool registration."""
    definition: ToolDefinition
    build_command: ToolCommandBuilder


class ToolRunManager:
    """Manages lifecycle of external tool processes: register, start, stop, status, SSE."""

    def __init__(
        self,
        runtime: MaaRuntime,
        configs: ConfigManager,
        run_state: RunStateStore,
        diagnostics: Diagnostics,
        framework_settings: FrameworkSettingsManager,
        run_coordinator: RunCoordinator,
    ) -> None:
        self.runtime = runtime
        self.configs = configs
        self.diagnostics = diagnostics
        self.framework_settings = framework_settings
        self.runs = GenericRunManager(
            run_state,
            self.diagnostics,
            run_coordinator,
            resource_wait_timeout_seconds=self.framework_settings.resource_wait_timeout_seconds,
        )
        self._specs = {
            "game-update": ToolSpec(
                definition=ToolDefinition(
                    id="game-update",
                    title="更新游戏",
                    description="下载并安装 B 服明日方舟 APK",
                    fields=(
                        ToolField(
                            id="address",
                            label="连接地址",
                            placeholder=DEFAULT_DEVICE_SERIAL,
                        ),
                    ),
                ),
                build_command=_build_game_update_command,
            )
        }

    def tools_response(self) -> dict[str, object]:
        return {
            "tools": [
                spec.definition.to_dict(default_config=self.default_config(spec.definition.id))
                for spec in self._specs.values()
            ],
            "current_run": self.current_response(),
        }

    def default_config(self, tool_id: str) -> dict[str, object]:
        if tool_id == "game-update":
            return {"address": self._default_connection_address()}
        return {}

    def start(self, tool_id: str, config: dict[str, object], *, retry_count: int = 1) -> LiveRun:
        spec = self._specs.get(tool_id)
        if spec is None:
            raise InvalidRequest(f"Unsupported tool: {tool_id}")

        sanitized_config = _sanitize_config(config)
        command = spec.build_command(self, sanitized_config)
        resources = self._tool_resources(tool_id, sanitized_config)
        run_id = uuid.uuid4().hex[:12]
        log_files = self.diagnostics.stream_log_files("tools", run_id)
        max_retries = _retry_count(retry_count)
        log_profile = plain_stream_log_profile("tool", diagnostic_sink=self.diagnostics.stream_sink("tools"))
        plan = RunStartPlan(
            kind="tool",
            title=spec.definition.title,
            command=CommandSpec(command.cmd, cwd=self.runtime.repo_root, env=command.env),
            max_retries=max_retries,
            timeouts=self.framework_settings.run_timeouts(),
            log_profile=log_profile,
            log_files=log_files,
            event_log_file=self.diagnostics.event_log_file(run_id),
            metadata={
                "tool_id": tool_id,
                "tool_title": spec.definition.title,
                "config": sanitized_config,
                "resource_locks": [resource.to_dict() for resource in resources],
                "run_priority": RUN_PRIORITY_NORMAL,
            },
            history_scope=("tools", tool_id),
            resources=resources,
            priority_name="normal",
            force_after_seconds=self._preemption_force_after_seconds(),
            text=RunTextTemplates(
                process_name="工具进程",
                completed="工具执行完成",
                exit_code="工具退出码: {return_code}",
                retry_next="准备重试工具运行。",
                start_failed="工具启动失败: {error}",
                stop_requested="收到停止请求，正在终止工具进程...",
                force_stop_requested="收到强制停止请求，正在强杀工具进程...",
                execution_failed="工具运行失败: {error}",
            ),
        )
        state = self.runs.start(plan, run_id=run_id)
        logger.info("tool run started run_id=%s tool_id=%s title=%s", run_id, tool_id, spec.definition.title)
        return state

    def current_response(self, *, include_logs: bool = True) -> dict[str, object]:
        return self.runs.current_response(include_logs=include_logs)

    def wait_for_change(self, last_version: int, timeout: float | None = None) -> int:
        return self.runs.wait_for_change(last_version, timeout)

    def stop_current(self) -> LiveRun:
        return self.runs.stop_current()

    def stop(self, run_id: str) -> LiveRun:
        return self.runs.stop(run_id)

    def force_stop_current(self) -> LiveRun:
        return self.runs.force_stop_current()

    def force_stop(self, run_id: str) -> LiveRun:
        return self.runs.force_stop(run_id)

    def _tool_resources(self, tool_id: str, config: dict[str, object]) -> tuple[RunResource, ...]:
        if tool_id != "game-update":
            return ()
        resource = adb_device_resource(config.get("address") or self._default_connection_address())
        return (resource,) if resource is not None else ()

    def _preemption_force_after_seconds(self) -> float | None:
        seconds = self.framework_settings.run_timeouts().stop_kill_seconds
        return float(seconds) if seconds > 0 else None

    def _default_connection_address(self) -> str:
        connection = dict_value(self._default_profile_data().get("connection"))
        return str(connection.get("address") or DEFAULT_DEVICE_SERIAL)

    def _default_adb_path(self) -> str:
        connection = dict_value(self._default_profile_data().get("connection"))
        return str(connection.get("adb_path") or "adb")

    def _default_profile_data(self) -> dict[str, Any]:
        try:
            data = self.configs.read_profile_config("default").get("data")
        except (FileNotFoundError, ValueError):
            return {}
        return dict_value(data)


def _build_game_update_command(manager: ToolRunManager, config: dict[str, object]) -> ToolCommand:
    address = str(config.get("address") or manager._default_connection_address()).strip()
    if not address:
        raise InvalidRequest("连接地址不能为空")
    return ToolCommand(
        cmd=[
            sys.executable,
            "-u",
            "-m",
            "maa_auto_panel.tools.game",
            "update-game",
            "--serial",
            address,
            "--adb",
            manager._default_adb_path(),
            "--download-dir",
            str(manager.runtime.download_dir),
        ],
        env=manager.runtime.env(),
    )


def _sanitize_config(config: dict[str, object]) -> dict[str, object]:
    return {str(key): value for key, value in config.items() if isinstance(key, str)}


def _retry_count(value: object) -> int:
    try:
        return min(50, max(1, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1
