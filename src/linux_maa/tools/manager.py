from __future__ import annotations

import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from linux_maa.config.app_settings import FrameworkSettingsManager
from linux_maa.config.manager import ConfigManager
from linux_maa.diagnostics import Diagnostics, get_logger
from linux_maa.logs.pipeline import LogSourceSpec, default_tone_for_source, plain_translate_line
from linux_maa.logs.state import RunLogBuffer
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.process import run_streaming_process
from linux_maa.run_coordinator import RUN_PRIORITY_NORMAL, RunCoordinator, RunLease, RunResource, adb_device_resource
from linux_maa.run_executor import LiveRetry, LiveRun, now_text
from linux_maa.run_state import RunStateStore
from linux_maa.settings import DEFAULT_DEVICE_SERIAL
from linux_maa.state import idle_response
from linux_maa.time_utils import server_now_iso
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


class ToolRunManager:
    """Manages lifecycle of external tool processes: register, start, stop, status, SSE."""
    def __init__(
        self,
        runtime: MaaRuntime,
        configs: ConfigManager,
        run_state: RunStateStore | None = None,
        diagnostics: Diagnostics | None = None,
        framework_settings: FrameworkSettingsManager | None = None,
        run_coordinator: RunCoordinator | None = None,
    ) -> None:
        self.runtime = runtime
        self.configs = configs
        self.run_state = run_state or RunStateStore(runtime)
        self.diagnostics = diagnostics or Diagnostics(runtime)
        self.framework_settings = framework_settings or FrameworkSettingsManager(runtime)
        self.run_coordinator = run_coordinator or RunCoordinator()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._version = 0
        self._runs: dict[str, LiveRun] = {}
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

    def start(self, tool_id: str, config: dict[str, object], *, retry_count: int = 1) -> LiveRun:
        spec = self._specs.get(tool_id)
        if spec is None:
            raise ValueError(f"Unsupported tool: {tool_id}")

        sanitized_config = _sanitize_config(config)
        resources = self._tool_resources(tool_id, sanitized_config)
        run_id = uuid.uuid4().hex[:12]
        started_at = now_text()
        log_files = self.diagnostics.tool_log_files(run_id)
        max_retries = _retry_count(retry_count)
        state = LiveRun(
            id=run_id,
            kind="tool",
            title=spec.definition.title,
            status="running",
            started_at=started_at,
            updated_at=started_at,
            max_retries=max_retries,
            log_files=log_files,
            event_log_file=self.diagnostics.event_log_file(run_id),
            metadata={
                "tool_id": tool_id,
                "tool_title": spec.definition.title,
                "config": sanitized_config,
                "retry_count": max_retries,
                "resource_locks": [resource.to_dict() for resource in resources],
                "run_priority": RUN_PRIORITY_NORMAL,
            },
        )
        lease = RunLease(
            run_id=run_id,
            kind="tool",
            title=spec.definition.title,
            priority=RUN_PRIORITY_NORMAL,
            resources=resources,
            request_stop=lambda: self._request_stop_for_run(state),
            request_force_stop=lambda: self._request_force_stop_for_run(state),
            force_after_seconds=self._preemption_force_after_seconds(),
        )
        try:
            self.run_coordinator.acquire(lease)
            with self._lock:
                current = self._runs.get(self._current_run_id or "")
                if current and current.status in {"running", "stopping"}:
                    raise RuntimeError(f"Tool already running: {current.title}")
                if state.stop_requested:
                    raise RuntimeError("Tool run was preempted before it started")

                self.run_state.create_run(
                    run_id=run_id,
                    kind="tool",
                    title=spec.definition.title,
                    max_retries=max_retries,
                    log_files=log_files,
                    event_log_file=state.event_log_file,
                    metadata={"tool_id": tool_id, "tool_title": spec.definition.title, "retry_count": max_retries},
                )
                self._runs[run_id] = state
                self._current_run_id = run_id
                logger.info("tool run started run_id=%s tool_id=%s title=%s", run_id, tool_id, spec.definition.title)
                self._notify_locked()
        except Exception:
            self.run_coordinator.release(run_id)
            raise

        thread = threading.Thread(target=self._run, args=(state, spec), daemon=True)
        state.thread = thread
        try:
            thread.start()
        except Exception:
            self.run_coordinator.release(run_id)
            raise
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

    def stop_current(self) -> LiveRun:
        with self._lock:
            state = self._runs.get(self._current_run_id or "")
            if state is None:
                raise KeyError("No tool run active")
            run_id = state.id
        return self.stop(run_id)

    def stop(self, run_id: str) -> LiveRun:
        with self._lock:
            state = self._runs.get(run_id)
            if state is None or state.status not in {"running", "stopping"}:
                raise KeyError("No tool run active")
            if state.status == "running":
                self.diagnostics.append_run_event(state.id, "tool", "framework", "收到停止请求，正在终止工具进程...\n", tone="warning")
                self._append_framework_event_locked(state, "收到停止请求，正在终止工具进程...", tone="warning")
                state.request_stop()
                logger.warning("tool stop requested run_id=%s tool_id=%s", state.id, state.metadata.get("tool_id"))
                self._notify_locked()
            return state

    def force_stop_current(self) -> LiveRun:
        with self._lock:
            state = self._runs.get(self._current_run_id or "")
            if state is None:
                raise KeyError("No tool run active")
            run_id = state.id
        return self.force_stop(run_id)

    def force_stop(self, run_id: str) -> LiveRun:
        with self._lock:
            state = self._runs.get(run_id)
            if state is None or state.status not in {"running", "stopping"}:
                raise KeyError("No tool run active")
            self.diagnostics.append_run_event(state.id, "tool", "framework", "收到强制停止请求，正在强杀工具进程...\n", tone="danger")
            self._append_framework_event_locked(state, "收到强制停止请求，正在强杀工具进程...", tone="danger")
            state.request_force_stop()
            logger.warning("tool force stop requested run_id=%s tool_id=%s", state.id, state.metadata.get("tool_id"))
            self._notify_locked()
            return state

    def _request_stop_for_run(self, state: LiveRun) -> None:
        with self._lock:
            managed = self._runs.get(state.id)
        if managed is None:
            state.request_stop()
            return
        self.stop(state.id)

    def _request_force_stop_for_run(self, state: LiveRun) -> None:
        with self._lock:
            managed = self._runs.get(state.id)
        if managed is None:
            state.request_force_stop()
            return
        self.force_stop(state.id)

    def _run(self, state: LiveRun, spec: ToolSpec) -> None:
        try:
            command = spec.build_command(self, dict(state.metadata.get("config")) if isinstance(state.metadata.get("config"), dict) else {})
        except Exception as exc:
            self._append_framework_event(state, f"工具配置无效: {exc}", tone="danger")
            logger.exception("tool command build failed run_id=%s tool_id=%s", state.id, state.metadata.get("tool_id"))
            if state.current_retry is not None:
                self._finish_retry(state, state.current_retry, "failed", None)
            self._finish_run(state, "failed", None)
            return

        final_status = "failed"
        final_return_code: int | None = None
        while len(state.retries) < state.max_retries and not state.stop_requested:
            retry = state.begin_retry(log=_new_tool_log_buffer(), log_files=state.log_files)
            if retry.retry_index == 1:
                self._append_framework_event(state, f"运行: {state.title}")
            else:
                self._append_framework_event(state, f"开始第 {retry.retry_index} 次重试", tone="warning")
            try:
                timeouts = self.framework_settings.run_timeouts()
                result = run_streaming_process(
                    self.runtime,
                    command.cmd,
                    env=command.env,
                    on_output=lambda text: None,
                    on_stream_output=lambda stream, text: self._append_stream_output(state, retry, stream, text),
                    on_process=lambda proc: self._set_process(state, proc),
                    should_stop=lambda: self._should_stop(state),
                    should_force_stop=lambda: state.force_stop_requested,
                    no_output_warning_seconds=timeouts.no_output_warning_seconds or None,
                    no_output_kill_seconds=timeouts.no_output_kill_seconds or None,
                    runtime_warning_seconds=timeouts.runtime_warning_seconds or None,
                    runtime_kill_seconds=timeouts.runtime_kill_seconds or None,
                    stop_warning_seconds=timeouts.stop_warning_seconds or None,
                    stop_kill_seconds=timeouts.stop_kill_seconds or None,
                    on_timeout=lambda level, elapsed: self._append_timeout_event(state, level, elapsed),
                )
                self._flush_tool_log(state, retry)
            except Exception as exc:
                self._append_framework_event(state, f"工具启动失败: {exc}", tone="danger")
                logger.exception("tool process failed run_id=%s tool_id=%s", state.id, state.metadata.get("tool_id"))
                self._finish_retry(state, retry, "failed", None)
                final_status = "failed"
                break

            final_return_code = result.return_code
            if result.stopped or state.status == "stopping":
                self._append_framework_event(state, f"工具退出码: {result.return_code}", tone="warning")
                self._finish_retry(state, retry, "stopped", result.return_code)
                final_status = "stopped"
                break
            if result.return_code == 0:
                self._append_framework_event(state, "工具执行完成", tone="success")
                self._finish_retry(state, retry, "succeeded", 0)
                final_status = "succeeded"
                break
            self._append_framework_event(state, f"工具退出码: {result.return_code}", tone="danger")
            self._finish_retry(state, retry, "failed", result.return_code)
            if len(state.retries) < state.max_retries:
                self._append_framework_event(state, "准备重试工具运行。", tone="warning")
        if state.stop_requested and final_status == "failed":
            final_status = "stopped"
        self._finish_run(state, final_status, final_return_code)

    def _append_stream_output(self, state: LiveRun, retry: LiveRetry, stream: str, text: str) -> None:
        self.diagnostics.append_tool_output(state.id, stream, text)
        if retry.log.append(text, source=f"tool:{stream}"):
            self._mark_log_updated(state, retry)

    def _flush_tool_log(self, state: LiveRun, retry: LiveRetry) -> None:
        if retry.log.flush():
            self._mark_log_updated(state, retry)

    def _mark_log_updated(self, state: LiveRun, retry: LiveRetry | None = None) -> None:
        with self._lock:
            if retry is not None:
                retry.touch()
            state.touch()
            self._notify_locked()

    def _append_framework_event(self, state: LiveRun, text: str, *, tone: str = "info") -> None:
        self.diagnostics.append_run_event(state.id, "tool", "framework", _ensure_newline(text), tone=tone)
        logger.info("tool event run_id=%s text=%s", state.id, text)
        with self._lock:
            self._append_framework_event_locked(state, text, tone=tone)
            self._notify_locked()

    def _append_framework_event_locked(self, state: LiveRun, text: str, *, tone: str = "info") -> None:
        retry = state.current_retry
        if retry is None:
            retry = state.begin_retry(log=_new_tool_log_buffer())
        if retry.log.append(_ensure_newline(text), source="framework:event", metadata={"time": server_now_iso(), "tone": tone}):
            retry.touch()
        state.touch()

    def _finish_retry(self, state: LiveRun, retry: LiveRetry, status: str, return_code: int | None) -> None:
        with self._lock:
            retry.seal(status=status, return_code=return_code)
            self._notify_locked()
        self.run_state.add_retry(
            retry_id=retry.id,
            run_id=state.id,
            retry_index=retry.retry_index,
            retry_group=retry.retry_group,
            status=status,
            started_at=retry.started_at,
            updated_at=retry.updated_at,
            ended_at=retry.ended_at or retry.updated_at,
            return_code=return_code,
            task_ids=retry.task_ids,
            task_results=retry.task_results,
            log_entries=retry.log.entries(),
            log_files=retry.log_files,
        )

    def _finish_run(self, state: LiveRun, status: str, return_code: int | None) -> None:
        try:
            with self._lock:
                state.finish(status=status, return_code=return_code)
                self._notify_locked()
            self.run_state.finish_run(state.id, status=status, return_code=return_code, retry_count=len(state.retries), retry_group_count=1)
            self.run_state.enforce_retention()
            self.diagnostics.enforce_retention()
            logger.info("tool run finished run_id=%s status=%s return_code=%s", state.id, status, return_code)
        finally:
            self.run_coordinator.release(state.id)

    def _append_timeout_event(self, state: LiveRun, level: str, elapsed: float) -> None:
        messages = {
            "no_output_warning": f"已 {elapsed:.0f}s 没有收到工具输出，工具可能卡住。",
            "no_output_kill": f"已 {elapsed:.0f}s 没有收到工具输出，正在强制终止。",
            "runtime_warning": f"工具运行时间已超过 {elapsed:.0f}s。",
            "runtime_kill": "工具运行时间已超过上限，正在强制终止。",
            "stop_warning": f"停止请求已等待 {elapsed:.0f}s，工具可能没有响应停止命令。",
            "stop_kill": "停止等待超过上限，正在强制终止工具。",
            "force_kill": "正在强制终止工具。",
        }
        tone = "warning" if level.endswith("warning") else "danger"
        self._append_framework_event(state, messages.get(level, f"工具超时事件: {level}"), tone=tone)

    def _set_process(self, state: LiveRun, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            state.process = proc

    def _should_stop(self, state: LiveRun) -> bool:
        with self._lock:
            return state.stop_requested

    def _notify_locked(self) -> None:
        self._version += 1
        self._condition.notify_all()

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


def _retry_count(value: object) -> int:
    try:
        return min(50, max(1, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1


def _register_tool_log_sources(log: RunLogBuffer) -> None:
    for source in ("tool:stdout", "tool:stderr"):
        log.register_source(LogSourceSpec(source, default_tone_for_source(source), plain_translate_line))


def _new_tool_log_buffer() -> RunLogBuffer:
    log = RunLogBuffer(max_output_chunks=2000)
    _register_tool_log_sources(log)
    return log
