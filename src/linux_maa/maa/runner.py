from __future__ import annotations

import json
import subprocess
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
import tomllib

from linux_maa.config.app_settings import FrameworkSettingsManager
from linux_maa.config.tasks import TASK_SUFFIXES, prepare_framework_task_config
from linux_maa.diagnostics import Diagnostics, get_logger
from linux_maa.logs.state import RunLogBuffer
from linux_maa.maa.log_templates import register_maa_log_sources
from linux_maa.maa.results import MaaTaskDescriptor, MaaTaskResultCollector
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.process import run_streaming_process
from linux_maa.run_executor import LiveRetry, LiveRun, now_text
from linux_maa.run_state import RunStateStore
from linux_maa.scheduler.models import TaskPolicy
from linux_maa.scheduler.policy import enabled_task_ids_from_config, retry_unfinished_task_ids, task_policies_from_config
from linux_maa.state import idle_response
from linux_maa.time_utils import server_now_iso
from linux_maa.utils import relative_path, resolve_existing_named_file, slugify, write_text_atomic


logger = get_logger(__name__)


def prepare_maa_cli_task(
    runtime: MaaRuntime,
    task: str,
    *,
    run_id: str,
    attempt: int,
    messages: list[str] | None = None,
    selected_task_ids: set[str] | None = None,
    force_enable_selected: bool = False,
    profile_data: dict[str, object] | None = None,
    profile_name: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Resolve task file, select items, write generated task JSON, return task name and env overrides."""
    source = resolve_task_file(runtime, task)
    data = load_task_file(source)
    if selected_task_ids is not None:
        data = select_task_items(data, selected_task_ids, force_enable_selected=force_enable_selected)
    sanitized = prepare_framework_task_config(data, runtime, messages)

    generated_name = f"linux-maa-{run_id}-attempt-{attempt}"
    generated_root = runtime.generated_config_dir / run_id
    generated_tasks = generated_root / "tasks"
    generated_tasks.mkdir(parents=True, exist_ok=True)
    ensure_generated_config_links(runtime, generated_root, skip_names={"profiles"} if profile_data is not None else None)
    if profile_data is not None:
        write_generated_profile(generated_root, profile_name or f"linux-maa-{run_id}", profile_data)

    generated_file = generated_tasks / f"{generated_name}.json"
    write_text_atomic(generated_file, json.dumps(sanitized, ensure_ascii=False, indent=2))

    env = runtime.env()
    env["MAA_CONFIG_DIR"] = str(generated_root)
    return generated_name, env


def select_task_items(data: dict[str, object], selected_task_ids: set[str], *, force_enable_selected: bool) -> dict[str, object]:
    """Filter task list to selected IDs, optionally force-enabling them."""
    selected = dict(data)
    tasks = selected.get("tasks")
    if not isinstance(tasks, list):
        return selected

    selected_tasks: list[object] = []
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            continue
        task_id = task_item_id(task, index)
        if task_id not in selected_task_ids:
            continue
        next_task = dict(task)
        if force_enable_selected:
            params = dict(next_task.get("params")) if isinstance(next_task.get("params"), dict) else {}
            params["enable"] = True
            next_task["params"] = params
        selected_tasks.append(next_task)
    selected["tasks"] = selected_tasks
    return selected


def task_item_id(task: dict[str, object], index: int) -> str:
    metadata = task.get("linux_maa")
    explicit = metadata.get("id") if isinstance(metadata, dict) else None
    if isinstance(explicit, str) and explicit.strip():
        return slugify(explicit) or f"task-{index}"
    task_type = str(task.get("type") or "Task")
    name = task.get("name")
    base = f"{task_type}-{name}" if isinstance(name, str) and name.strip() else task_type
    return slugify(base) or f"task-{index}"


def write_generated_profile(generated_root: Path, profile_name: str, profile_data: dict[str, object]) -> Path:
    profiles_dir = generated_root / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{slugify(profile_name) or 'profile'}.json"
    path = profiles_dir / filename
    write_text_atomic(path, json.dumps(profile_data, ensure_ascii=False, indent=2))
    return path


def resolve_task_file(runtime: MaaRuntime, task: str) -> Path:
    tasks_dir = runtime.config_dir / "tasks"
    return resolve_existing_named_file(tasks_dir, task, suffixes=TASK_SUFFIXES, label="task name")


def load_task_file(path: Path) -> dict[str, object]:
    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".toml":
        return tomllib.loads(content)
    if path.suffix.lower() == ".json":
        loaded = json.loads(content)
        if isinstance(loaded, dict):
            return loaded
        raise ValueError("Task JSON root must be an object")
    raise ValueError(f"Cannot generate maa-cli task from {path.suffix} config yet")


def ensure_generated_config_links(runtime: MaaRuntime, generated_root: Path, *, skip_names: set[str] | None = None) -> None:
    runtime.config_dir.mkdir(parents=True, exist_ok=True)
    skip = skip_names or set()
    for source in runtime.config_dir.iterdir():
        if source.name == "tasks" or source.name in skip:
            continue
        target = generated_root / source.name
        if target.exists():
            continue
        target.symlink_to(source, target_is_directory=source.is_dir())


@dataclass(frozen=True)
class MaaRunRequest:
    """Immutable request: which task and profile to run, at what log level."""
    task: str
    profile: str = "default"
    log_level: int = 1
    retry_count: int = 1


class MaaRunManager:
    """Orchestrates manual MAA task runs: start, stop, status, SSE change notification."""
    def __init__(
        self,
        runtime: MaaRuntime,
        run_state: RunStateStore | None = None,
        diagnostics: Diagnostics | None = None,
        framework_settings: FrameworkSettingsManager | None = None,
    ) -> None:
        self.runtime = runtime
        self.run_state = run_state or RunStateStore(runtime)
        self.diagnostics = diagnostics or Diagnostics(runtime)
        self.framework_settings = framework_settings or FrameworkSettingsManager(runtime)
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._version = 0
        self._runs: dict[str, LiveRun] = {}
        self._current_run_id: str | None = None

    def start(self, request: MaaRunRequest) -> LiveRun:
        with self._lock:
            current = self._runs.get(self._current_run_id or "")
            if current and current.status == "running":
                raise RuntimeError(f"Run already active: {current.id}")

            run_id = uuid.uuid4().hex[:12]
            started_at = now_text()
            log_files = self.diagnostics.maa_cli_log_files(run_id)
            max_retries = _retry_count(request.retry_count)
            state = LiveRun(
                id=run_id,
                kind="manual",
                title=request.task,
                status="running",
                started_at=started_at,
                updated_at=started_at,
                max_retries=max_retries,
                log_files=log_files,
                event_log_file=self.diagnostics.event_log_file(run_id),
                metadata={"task": request.task, "profile": request.profile, "log_level": request.log_level, "retry_count": max_retries},
            )
            self.run_state.create_run(
                run_id=run_id,
                kind="manual",
                title=request.task,
                max_retries=max_retries,
                log_files=log_files,
                event_log_file=state.event_log_file,
                metadata={"task": request.task, "profile": request.profile, "retry_count": max_retries},
            )
            logger.info("manual run started run_id=%s task=%s profile=%s log_level=%s", run_id, request.task, request.profile, request.log_level)
            self._runs[run_id] = state
            self._current_run_id = run_id
            self._notify_locked()

        thread = threading.Thread(target=self._run, args=(state,), daemon=True)
        state.thread = thread
        thread.start()
        return state

    def wait_for_change(self, last_version: int, timeout: float | None = None) -> int:
        with self._condition:
            if self._version == last_version:
                self._condition.wait(timeout)
            return self._version

    def current(self) -> LiveRun | None:
        with self._lock:
            return self._runs.get(self._current_run_id or "")

    def current_response(self, *, include_logs: bool = True) -> dict[str, object]:
        with self._lock:
            state = self._runs.get(self._current_run_id or "")
            version = self._version
            payload = state.to_dict(include_logs=include_logs) if state is not None else idle_response()
        payload["stream_version"] = version
        return payload

    def get(self, run_id: str) -> LiveRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def stop(self, run_id: str) -> LiveRun:
        state = self.get(run_id)
        if state is None:
            raise KeyError(run_id)
        with self._lock:
            if state.status in {"running", "stopping"}:
                self._append_framework_log_locked(state, "收到停止请求，正在等待 maa-cli 自行停止...", tone="warning")
                logger.warning("manual run stop requested run_id=%s", state.id)
                state.request_stop()
                self._notify_locked()
        return state

    def force_stop(self, run_id: str) -> LiveRun:
        state = self.get(run_id)
        if state is None:
            raise KeyError(run_id)
        with self._lock:
            if state.status in {"running", "stopping"}:
                self._append_framework_log_locked(state, "收到强制停止请求，正在强杀 maa-cli...", tone="danger")
                logger.warning("manual run force stop requested run_id=%s", state.id)
                state.request_force_stop()
                self._notify_locked()
        return state

    def _mark_log_updated(self, state: LiveRun, retry: LiveRetry | None = None) -> None:
        with self._lock:
            if retry is not None:
                retry.touch()
            state.touch()
            self._notify_locked()

    def _append_maa_log(self, state: LiveRun, retry: LiveRetry, text: str, stream: str = "output") -> None:
        self.diagnostics.append_maa_cli_output(state.id, stream, text)
        if retry.log.append(text, source=f"maa-cli:{stream}"):
            self._mark_log_updated(state, retry)

    def _flush_maa_log(self, state: LiveRun, retry: LiveRetry) -> None:
        if retry.log.flush():
            self._mark_log_updated(state, retry)

    def _append_framework_log(self, state: LiveRun, text: str, *, tone: str = "info") -> None:
        self.diagnostics.append_run_event(state.id, "manual", "framework", text)
        logger.info("manual run event run_id=%s text=%s", state.id, text)
        with self._lock:
            self._append_framework_log_locked(state, text, tone=tone)
            self._notify_locked()

    def _append_framework_log_locked(self, state: LiveRun, text: str, *, tone: str = "info") -> None:
        retry = state.current_retry
        if retry is None:
            retry = state.begin_retry(log=_new_maa_log_buffer())
        if retry.log.append(f"{text.rstrip()}\n", source="framework:event", metadata={"time": server_now_iso(), "tone": tone}):
            retry.touch()
        state.touch()

    def _finish_retry(self, state: LiveRun, retry: LiveRetry, status: str, return_code: int | None, *, task_results: list[dict[str, object]], maacore_log_file: str | None = None) -> None:
        with self._lock:
            retry.task_results = task_results
            retry.seal(status=status, return_code=return_code)
            if maacore_log_file is not None:
                retry.maacore_log_file = maacore_log_file
                state.maacore_log_file = maacore_log_file
            self._notify_locked()
        generated_config_dir = relative_path(self.runtime.generated_config_dir / state.id, self.runtime.repo_root)
        retry.generated_config_dir = generated_config_dir
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
            task_results=task_results,
            log_entries=retry.log.entries(),
            log_files=retry.log_files,
            generated_config_dir=generated_config_dir,
            maacore_log_file=maacore_log_file,
        )

    def _finish_run(self, state: LiveRun, status: str, return_code: int | None) -> None:
        with self._lock:
            state.finish(status=status, return_code=return_code)
            self._notify_locked()
        generated_config_dir = relative_path(self.runtime.generated_config_dir / state.id, self.runtime.repo_root)
        self.run_state.finish_run(
            state.id,
            status=status,
            return_code=return_code,
            maacore_log_file=state.maacore_log_file,
            generated_config_dir=generated_config_dir,
            retry_count=len(state.retries),
            retry_group_count=1,
            summary={
                "task_results": state.retries[-1].task_results if state.retries else [],
                "generated_config_dir": generated_config_dir,
            },
        )
        self.run_state.enforce_retention()
        self.diagnostics.enforce_retention()
        logger.info("manual run finished run_id=%s status=%s return_code=%s maacore_log_file=%s", state.id, status, return_code, state.maacore_log_file)

    def _run(self, state: LiveRun) -> None:
        task = str(state.metadata.get("task") or state.title)
        profile = str(state.metadata.get("profile") or "default")
        log_level = int(state.metadata.get("log_level") or 0)
        task_data = load_task_file(resolve_task_file(self.runtime, task))
        policies = task_policies_from_config(task_data)
        policy_by_id = {policy.id: policy for policy in policies}
        selected_task_ids = enabled_task_ids_from_config(task_data)
        if not selected_task_ids:
            self._append_framework_log(state, "当前任务配置没有启用的子任务。", tone="warning")
            self._finish_run(state, "skipped", 0)
            return

        next_task_ids = selected_task_ids
        run_successful_task_ids: set[str] = set()
        final_status = "failed"
        final_return_code: int | None = None

        while next_task_ids and len(state.retries) < state.max_retries and not state.stop_requested:
            attempt_index = len(state.retries) + 1
            retry = state.begin_retry(task_ids=next_task_ids, log=_new_maa_log_buffer(), log_files=state.log_files)
            prepare_messages: list[str] = []
            run_task, run_env = prepare_maa_cli_task(
                self.runtime,
                task,
                run_id=state.id,
                attempt=attempt_index,
                messages=prepare_messages,
                selected_task_ids=set(next_task_ids),
                force_enable_selected=True,
            )
            cmd = [
                str(self.runtime.maa_bin),
                "run",
                run_task,
                "--batch",
                "--profile",
                profile,
            ]
            if log_level > 0:
                cmd.extend(["-v"] * log_level)
            if attempt_index == 1:
                self._append_framework_log(state, f"运行: {task}")
            self._append_framework_log(state, f"开始第 {attempt_index} 次尝试: {', '.join(_task_names(policy_by_id, next_task_ids))}", tone="info")
            for message in prepare_messages:
                self._append_framework_log(state, message)
            task_descriptors = _task_descriptors(policy_by_id, next_task_ids)
            retry.log.begin_task_sequence(_task_descriptor_dicts(task_descriptors))
            collector = MaaTaskResultCollector(task_descriptors)
            maacore_log_start = self.diagnostics.maacore_log_offset()
            try:
                result = self._run_process(state, retry, cmd, run_env, collector)
            except Exception as exc:
                self._append_framework_log(state, f"启动 maa-cli 失败: {exc}")
                logger.exception("manual run process start failed run_id=%s", state.id)
                collector.finish()
                self._finish_retry(state, retry, "failed", None, task_results=collector.results)
                self._finish_run(state, "failed", None)
                return
            collector.finish()
            maacore_log_file = self.diagnostics.capture_maacore_log(retry.id, maacore_log_start)
            task_results = list(collector.results)
            status_by_task_id = collector.status_by_task_id(next_task_ids)
            run_successful_task_ids.update(task_id for task_id, status in status_by_task_id.items() if status == "succeeded")

            attempt_status = "succeeded" if result.return_code == 0 and all(status == "succeeded" for status in status_by_task_id.values()) else "failed"
            if result.stopped or state.stop_requested:
                attempt_status = "stopped"
            if result.timed_out:
                attempt_status = "failed"
            self._append_framework_log(state, f"maa-cli 退出码: {result.return_code}", tone="info" if result.return_code == 0 else "warning")
            self._finish_retry(state, retry, attempt_status, result.return_code, task_results=task_results, maacore_log_file=maacore_log_file)
            final_return_code = result.return_code

            if attempt_status == "stopped":
                final_status = "stopped"
                break
            next_task_ids = retry_unfinished_task_ids(selected_task_ids, status_by_task_id, run_successful_task_ids=run_successful_task_ids)
            if not next_task_ids:
                final_status = "succeeded"
                break
            if len(state.retries) < state.max_retries:
                self._append_framework_log(state, f"准备重试: {', '.join(_task_names(policy_by_id, next_task_ids))}", tone="warning")

        if state.stop_requested and final_status not in {"stopped", "succeeded"}:
            final_status = "stopped"
        elif next_task_ids and final_status != "stopped":
            self._append_framework_log(state, "重试次数已达上限，仍有未成功子任务。", tone="danger")
            final_status = "failed"
        self._finish_run(state, final_status, final_return_code)

    def _run_process(self, state: LiveRun, retry: LiveRetry, cmd: list[str], env: dict[str, str], collector: MaaTaskResultCollector):
        try:
            timeouts = self.framework_settings.run_timeouts()
            result = run_streaming_process(
                self.runtime,
                cmd,
                env=env,
                on_output=lambda text: None,
                on_stream_output=lambda stream, text: self._append_maa_log(state, retry, text, stream),
                on_raw_line=lambda stream, line: collector.consume_raw_line(f"maa-cli:{stream}", line),
                on_process=lambda proc: self._set_process(state, proc),
                should_stop=lambda: state.stop_requested,
                should_force_stop=lambda: state.force_stop_requested,
                no_output_warning_seconds=timeouts.no_output_warning_seconds or None,
                no_output_kill_seconds=timeouts.no_output_kill_seconds or None,
                runtime_warning_seconds=timeouts.runtime_warning_seconds or None,
                runtime_kill_seconds=timeouts.runtime_kill_seconds or None,
                stop_warning_seconds=timeouts.stop_warning_seconds or None,
                stop_kill_seconds=timeouts.stop_kill_seconds or None,
                on_timeout=lambda level, elapsed: self._append_timeout_event(state, level, elapsed),
            )
            return result
        finally:
            self._flush_maa_log(state, retry)

    def _append_timeout_event(self, state: LiveRun, level: str, elapsed: float) -> None:
        messages = {
            "no_output_warning": f"已 {elapsed:.0f}s 没有收到新输出，运行可能卡住。",
            "no_output_kill": f"已 {elapsed:.0f}s 没有收到新输出，正在强制终止 maa-cli。",
            "runtime_warning": f"运行时间已超过 {elapsed:.0f}s。",
            "runtime_kill": "运行时间已超过上限，正在强制终止 maa-cli。",
            "stop_warning": f"停止请求已等待 {elapsed:.0f}s，maa-cli 可能没有响应停止命令。",
            "stop_kill": "停止等待超过上限，正在强制终止 maa-cli。",
            "force_kill": "正在强制终止 maa-cli。",
        }
        tone = "warning" if level.endswith("warning") else "danger"
        self._append_framework_log(state, messages.get(level, f"运行超时事件: {level}"), tone=tone)

    def _set_process(self, state: LiveRun, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            state.process = proc

    def _notify_locked(self) -> None:
        self._version += 1
        self._condition.notify_all()


def _register_maa_cli_log_sources(log: RunLogBuffer) -> None:
    register_maa_log_sources(log)


def _new_maa_log_buffer() -> RunLogBuffer:
    log = RunLogBuffer(max_output_chunks=2000)
    _register_maa_cli_log_sources(log)
    return log


def _retry_count(value: object) -> int:
    try:
        return min(50, max(1, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1


def _task_descriptors(policy_by_id: dict[str, TaskPolicy], task_ids: list[str]) -> list[MaaTaskDescriptor]:
    return [
        MaaTaskDescriptor(task_id=task_id, source_name=policy_by_id[task_id].type, name=policy_by_id[task_id].name)
        for task_id in task_ids
        if task_id in policy_by_id
    ]


def _task_descriptor_dicts(descriptors: list[MaaTaskDescriptor]) -> list[dict[str, str]]:
    return [{"task_id": item.task_id, "source_name": item.source_name, "name": item.name} for item in descriptors]


def _task_names(policy_by_id: dict[str, TaskPolicy], task_ids: list[str]) -> list[str]:
    return [policy_by_id[task_id].name if task_id in policy_by_id else task_id for task_id in task_ids]
