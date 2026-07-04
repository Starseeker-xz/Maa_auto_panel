from __future__ import annotations

import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from linux_maa.config import ConfigManager
from linux_maa.diagnostics import Diagnostics, get_logger
from linux_maa.logs import LogSourceSpec, RunLogBuffer, plain_translate_line
from linux_maa.logs.pipeline import default_tone_for_source
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.process import run_streaming_process
from linux_maa.run_state import RunStateStore
from linux_maa.settings import DEFAULT_DEVICE_SERIAL
from linux_maa.state import idle_response
from linux_maa.utils import dict_value


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


@dataclass
class ToolRunState:
    """Mutable runtime state for a single tool execution: status, config, return code, logs."""
    id: str
    tool_id: str
    tool_title: str
    status: str
    created_at: str
    updated_at: str
    config: dict[str, object] = field(default_factory=dict)
    return_code: int | None = None
    log_file: str | None = None
    log_files: dict[str, str] = field(default_factory=dict)
    log: RunLogBuffer = field(default_factory=lambda: RunLogBuffer(max_output_chunks=2000))
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    stop_requested: bool = False

    def to_dict(self, *, include_logs: bool = True) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "tool_id": self.tool_id,
            "tool_title": self.tool_title,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "config": dict(self.config),
            "return_code": self.return_code,
            "log_file": self.log_file,
            "log_files": dict(self.log_files),
        }
        if include_logs:
            data.update(self.log.to_dict())
        return data


class ToolRunManager:
    """Manages lifecycle of external tool processes: register, start, stop, status, SSE."""
    def __init__(
        self,
        runtime: MaaRuntime,
        configs: ConfigManager,
        run_state: RunStateStore | None = None,
        diagnostics: Diagnostics | None = None,
    ) -> None:
        self.runtime = runtime
        self.configs = configs
        self.run_state = run_state or RunStateStore(runtime)
        self.diagnostics = diagnostics or Diagnostics(runtime)
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._version = 0
        self._runs: dict[str, ToolRunState] = {}
        self._current_run_id: str | None = None
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

    def start(self, tool_id: str, config: dict[str, object]) -> ToolRunState:
        spec = self._specs.get(tool_id)
        if spec is None:
            raise ValueError(f"Unsupported tool: {tool_id}")

        sanitized_config = _sanitize_config(config)
        with self._lock:
            current = self._runs.get(self._current_run_id or "")
            if current and current.status in {"running", "stopping"}:
                raise RuntimeError(f"Tool already running: {current.tool_title}")

            now = datetime.now().isoformat(timespec="seconds")
            run_id = uuid.uuid4().hex[:12]
            state = ToolRunState(
                id=run_id,
                tool_id=tool_id,
                tool_title=spec.definition.title,
                status="running",
                created_at=now,
                updated_at=now,
                config=sanitized_config,
            )
            state.log_file = self.diagnostics.tool_log_file(run_id)
            state.log_files = self.diagnostics.tool_log_files(run_id)
            _register_tool_log_sources(state.log)
            self.run_state.create_tool_run(
                run_id=run_id,
                tool_id=tool_id,
                title=spec.definition.title,
                log_file=state.log_file,
                log_files=state.log_files,
                event_log_file=self.diagnostics.event_log_file(run_id),
            )
            self._runs[run_id] = state
            self._current_run_id = run_id
            logger.info("tool run started run_id=%s tool_id=%s title=%s", run_id, tool_id, spec.definition.title)
            self._notify_locked()

        thread = threading.Thread(target=self._run, args=(state, spec), daemon=True)
        thread.start()
        return state

    def current_response(self, *, include_logs: bool = True) -> dict[str, object]:
        with self._lock:
            state = self._runs.get(self._current_run_id or "")
            version = self._version
            payload = state.to_dict(include_logs=include_logs) if state is not None else idle_response()
        payload["stream_version"] = version
        return payload

    def wait_for_change(self, last_version: int, timeout: float | None = None) -> int:
        with self._condition:
            if self._version == last_version:
                self._condition.wait(timeout)
            return self._version

    def stop_current(self) -> ToolRunState:
        with self._lock:
            state = self._runs.get(self._current_run_id or "")
            if state is None or state.status not in {"running", "stopping"}:
                raise KeyError("No tool run active")
            if state.status == "running":
                state.stop_requested = True
                state.status = "stopping"
                state.updated_at = datetime.now().isoformat(timespec="seconds")
                self.diagnostics.append_run_event(state.id, "tool", "framework", "收到停止请求，正在终止工具进程...\n", tone="warning")
                self._append_framework_event_locked(state, "收到停止请求，正在终止工具进程...", tone="warning")
                logger.warning("tool stop requested run_id=%s tool_id=%s", state.id, state.tool_id)
                self._notify_locked()
            return state

    def _run(self, state: ToolRunState, spec: ToolSpec) -> None:
        try:
            command = spec.build_command(self, state.config)
        except Exception as exc:
            self._append_framework_event(state, f"工具配置无效: {exc}", tone="danger")
            logger.exception("tool command build failed run_id=%s tool_id=%s", state.id, state.tool_id)
            self._set_done(state, "failed", None)
            return

        self._append_framework_event(state, f"运行: {state.tool_title}")
        try:
            result = run_streaming_process(
                self.runtime,
                command.cmd,
                env=command.env,
                on_output=lambda text: None,
                on_stream_output=lambda stream, text: self._append_stream_output(state, stream, text),
                on_process=lambda proc: self._set_process(state, proc),
                should_stop=lambda: self._should_stop(state),
            )
            self._flush_tool_log(state)
        except Exception as exc:
            self._append_framework_event(state, f"工具启动失败: {exc}", tone="danger")
            logger.exception("tool process failed run_id=%s tool_id=%s", state.id, state.tool_id)
            self._set_done(state, "failed", None)
            return

        return_code = result.return_code
        if result.stopped or state.status == "stopping":
            self._append_framework_event(state, f"工具退出码: {return_code}", tone="warning")
            self._set_done(state, "stopped", return_code)
        elif return_code == 0:
            self._append_framework_event(state, "工具执行完成", tone="success")
            self._set_done(state, "succeeded", 0)
        else:
            self._append_framework_event(state, f"工具退出码: {return_code}", tone="danger")
            self._set_done(state, "failed", return_code)

    def _append_stream_output(self, state: ToolRunState, stream: str, text: str) -> None:
        self.diagnostics.append_tool_output(state.id, stream, text)
        if state.log.append(text, source=f"tool:{stream}"):
            self._mark_log_updated(state)

    def _flush_tool_log(self, state: ToolRunState) -> None:
        if state.log.flush():
            self._mark_log_updated(state)

    def _mark_log_updated(self, state: ToolRunState) -> None:
        with self._lock:
            state.updated_at = datetime.now().isoformat(timespec="seconds")
            self._notify_locked()

    def _append_framework_event(self, state: ToolRunState, text: str, *, tone: str = "info") -> None:
        self.diagnostics.append_run_event(state.id, "tool", "framework", _ensure_newline(text), tone=tone)
        logger.info("tool event run_id=%s text=%s", state.id, text)
        with self._lock:
            self._append_framework_event_locked(state, text, tone=tone)
            self._notify_locked()

    def _append_framework_event_locked(self, state: ToolRunState, text: str, *, tone: str = "info") -> None:
        state.log.append(_ensure_newline(text), source="framework:event", metadata={"time": datetime.now().strftime("%H:%M:%S"), "tone": tone})
        state.updated_at = datetime.now().isoformat(timespec="seconds")

    def _set_done(self, state: ToolRunState, status: str, return_code: int | None) -> None:
        with self._lock:
            state.status = status
            state.return_code = return_code
            state.process = None
            state.updated_at = datetime.now().isoformat(timespec="seconds")
            self._notify_locked()
        self.run_state.add_single_attempt(
            run_id=state.id,
            status=status,
            started_at=state.created_at,
            ended_at=state.updated_at,
            return_code=return_code,
            task_results=state.log.task_results(),
            log_entries=state.log.entries(),
            log_file=state.log_file,
            log_files=state.log_files,
        )
        self.run_state.finish_generic_run(state.id, status=status, return_code=return_code)
        self.run_state.enforce_retention()
        self.diagnostics.enforce_retention()
        logger.info("tool run finished run_id=%s status=%s return_code=%s", state.id, status, return_code)

    def _set_process(self, state: ToolRunState, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            state.process = proc

    def _should_stop(self, state: ToolRunState) -> bool:
        with self._lock:
            return state.stop_requested

    def _notify_locked(self) -> None:
        self._version += 1
        self._condition.notify_all()

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
        raise ValueError("连接地址不能为空")
    return ToolCommand(
        cmd=[
            sys.executable,
            "-u",
            "-m",
            "linux_maa.tools.game",
            "update-game",
            "--serial",
            address,
            "--adb",
            manager._default_adb_path(),
            "--download-dir",
            str(manager.runtime.repo_root / "downloads"),
        ],
        env=manager.runtime.env(),
    )


def _sanitize_config(config: dict[str, object]) -> dict[str, object]:
    return {str(key): value for key, value in config.items() if isinstance(key, str)}


def _ensure_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"


def _register_tool_log_sources(log: RunLogBuffer) -> None:
    for source in ("tool:stdout", "tool:stderr"):
        log.register_source(LogSourceSpec(source, default_tone_for_source(source), plain_translate_line))
