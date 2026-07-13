from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
import tomllib

from maa_auto_panel.config.app_settings import FrameworkSettingsManager
from maa_auto_panel.config.manager import ConfigManager
from maa_auto_panel.config.tasks import TASK_SUFFIXES, prepare_framework_task_config
from maa_auto_panel.diagnostics import Diagnostics, get_logger
from maa_auto_panel.errors import CorruptState
from maa_auto_panel.maa.cleanup import enforce_maa_debug_retention
from maa_auto_panel.maa.log_templates import register_maa_log_sources
from maa_auto_panel.maa.results import MaaTaskDescriptor, MaaTaskResultCollector
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.notifications import NotificationService
from maa_auto_panel.process import StreamingProcessResult
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.contracts import RetryDecision, RunCallbacks, RunStartPlan, RunTextTemplates
from maa_auto_panel.run_manager.coordinator import RunCoordinator
from maa_auto_panel.run_manager.logs import RunLogProfile
from maa_auto_panel.run_manager.manager import GenericRunManager, RunAttempt
from maa_auto_panel.run_manager.state import LiveRun
from maa_auto_panel.run_manager.store import RunStateStore
from maa_auto_panel.run_resources import RUN_PRIORITY_NORMAL, maa_run_resources_from_profile
from maa_auto_panel.scheduler.models import TaskPolicy
from maa_auto_panel.scheduler.policy import enabled_task_ids_from_config, retry_unfinished_task_ids, task_policies_from_config
from maa_auto_panel.utils import dict_value, resolve_existing_named_file, slugify, write_text_atomic


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

    generated_name = f"framework-{run_id}-attempt-{attempt}"
    generated_root = runtime.generated_config_dir / run_id
    generated_tasks = generated_root / "tasks"
    generated_tasks.mkdir(parents=True, exist_ok=True)
    ensure_generated_config_links(runtime, generated_root, skip_names={"profiles"} if profile_data is not None else None)
    if profile_data is not None:
        write_generated_profile(generated_root, profile_name or f"framework-{run_id}", profile_data)

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
    metadata = task.get("framework")
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
    try:
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".toml":
            return tomllib.loads(content)
        if path.suffix.lower() == ".json":
            loaded = json.loads(content)
            if isinstance(loaded, dict):
                return loaded
            raise CorruptState(f"Task JSON root must be an object: {path}")
    except (UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise CorruptState(f"Cannot parse task config: {path}") from exc
    raise CorruptState(f"Cannot generate maa-cli task from {path.suffix} config: {path}")


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


@dataclass
class ManualMaaRunCallbacks:
    """Manual MAA attempt hooks; GenericRunManager owns lifecycle and retry loop."""

    runtime: MaaRuntime
    diagnostics: Diagnostics
    request: MaaRunRequest
    policies: list[TaskPolicy]
    selected_task_ids: list[str]

    def __post_init__(self) -> None:
        self.policy_by_id = {policy.id: policy for policy in self.policies}
        self.run_successful_task_ids: set[str] = set()
        self.collectors: dict[str, MaaTaskResultCollector] = {}
        self.maacore_log_offsets: dict[str, int] = {}

    def to_callbacks(self) -> RunCallbacks:
        return RunCallbacks(
            on_start=self.on_start,
            build_command=self.build_command,
            on_raw_line=self.on_raw_line,
            evaluate_attempt=self.evaluate_attempt,
            after_attempt=self.after_attempt,
        )

    def on_start(self, attempt: RunAttempt) -> RetryDecision | None:
        if self.selected_task_ids:
            return None
        generated_config_dir = _generated_config_dir(self.runtime, attempt.run_id)
        attempt.add_event("当前任务配置没有启用的子任务。", tone="warning")
        return RetryDecision(
            "skipped",
            0,
            run_status="skipped",
            retry_metadata={"task_results": []},
            retry_artifacts={"generated_config_dir": generated_config_dir},
            summary_patch={"task_results": [], "generated_config_dir": generated_config_dir},
        )

    def build_command(self, attempt: RunAttempt) -> CommandSpec:
        task_ids = _attempt_task_ids(attempt)
        prepare_messages: list[str] = []
        run_task, run_env = prepare_maa_cli_task(
            self.runtime,
            self.request.task,
            run_id=attempt.run_id,
            attempt=attempt.attempt_index,
            messages=prepare_messages,
            selected_task_ids=set(task_ids),
            force_enable_selected=True,
        )
        cmd = [
            str(self.runtime.maa_bin),
            "run",
            run_task,
            "--batch",
            "--profile",
            self.request.profile,
        ]
        if self.request.log_level > 0:
            cmd.extend(["-v"] * self.request.log_level)
        attempt.add_event(f"开始第 {attempt.attempt_index} 次尝试: {', '.join(_task_names(self.policy_by_id, task_ids))}", tone="info")
        for message in prepare_messages:
            attempt.add_event(message, tone="info")

        task_descriptors = _task_descriptors(self.policy_by_id, task_ids)
        attempt.configure_log(lambda log: log.begin_task_sequence(_task_descriptor_dicts(task_descriptors)))
        self.collectors[attempt.retry_id] = MaaTaskResultCollector(task_descriptors)
        self.maacore_log_offsets[attempt.retry_id] = current_log_offset(maacore_log_source(self.runtime))
        return CommandSpec(cmd, cwd=self.runtime.repo_root, env=run_env)

    def on_raw_line(self, attempt: RunAttempt, stream: str, line: str) -> None:
        collector = self.collectors.get(attempt.retry_id)
        if collector is not None:
            collector.consume_raw_line(f"maa-cli:{stream}", line)

    def evaluate_attempt(self, attempt: RunAttempt, result: StreamingProcessResult) -> RetryDecision:
        generated_config_dir = _generated_config_dir(self.runtime, attempt.run_id)
        collector = self.collectors.pop(attempt.retry_id, MaaTaskResultCollector([]))
        collector.finish()
        maacore_capture = self.diagnostics.capture_file_increment(
            maacore_log_source(self.runtime),
            self.maacore_log_offsets.pop(attempt.retry_id, 0),
            capture_id=attempt.retry_id,
        )
        enforce_maa_debug_retention(self.runtime.layout.maa)
        task_results = list(collector.results)
        task_ids = _attempt_task_ids(attempt)
        status_by_task_id = collector.status_by_task_id(task_ids)
        self.run_successful_task_ids.update(task_id for task_id, status in status_by_task_id.items() if status == "succeeded")

        attempt_status = "succeeded" if result.return_code == 0 and all(status == "succeeded" for status in status_by_task_id.values()) else "failed"
        if result.stopped or attempt.stop_requested:
            attempt_status = "stopped"
        if result.timed_out:
            attempt_status = "failed"

        next_task_ids: list[str] = []
        if attempt_status != "stopped":
            next_task_ids = retry_unfinished_task_ids(
                self.selected_task_ids,
                status_by_task_id,
                run_successful_task_ids=self.run_successful_task_ids,
            )
        will_retry = bool(next_task_ids) and attempt.attempt_index < attempt.max_retries and attempt_status != "stopped"
        run_status = None
        if attempt_status == "stopped":
            run_status = "stopped"
        elif not next_task_ids:
            run_status = "succeeded"
        elif not will_retry:
            run_status = "failed"

        return RetryDecision(
            attempt_status,
            result.return_code,
            run_status=run_status,
            continue_retry=will_retry,
            next_attempt_payload={"task_ids": next_task_ids},
            retry_metadata={"task_ids": task_ids, "task_results": task_results},
            retry_artifacts={"generated_config_dir": generated_config_dir, "diagnostic_log_file": maacore_capture.log_file},
            summary_patch={"task_results": task_results, "generated_config_dir": generated_config_dir},
        )

    def after_attempt(
        self,
        attempt: RunAttempt,
        _result: StreamingProcessResult,
        decision: RetryDecision,
    ) -> RetryDecision | None:
        if attempt.stop_requested or decision.retry_status == "stopped":
            return None
        next_task_ids = _payload_task_ids(decision.next_attempt_payload or {})
        if decision.continue_retry and next_task_ids:
            attempt.add_event(f"准备重试: {', '.join(_task_names(self.policy_by_id, next_task_ids))}", tone="warning")
        elif next_task_ids and attempt.attempt_index >= attempt.max_retries:
            attempt.add_event("重试次数已达上限，仍有未成功子任务。", tone="danger")
        return None


class MaaRunManager:
    """Orchestrates manual MAA task runs: start, stop, status, SSE change notification."""

    def __init__(
        self,
        runtime: MaaRuntime,
        run_state: RunStateStore,
        diagnostics: Diagnostics,
        framework_settings: FrameworkSettingsManager,
        configs: ConfigManager,
        run_coordinator: RunCoordinator,
        notifications: NotificationService | None = None,
    ) -> None:
        self.runtime = runtime
        self.run_state = run_state
        self.diagnostics = diagnostics
        self.framework_settings = framework_settings
        self.configs = configs
        self.run_coordinator = run_coordinator
        self.runs = GenericRunManager(
            self.run_state,
            self.diagnostics,
            self.run_coordinator,
            on_run_finished=notifications.notify_run_finished if notifications else None,
            resource_wait_timeout_seconds=self.framework_settings.resource_wait_timeout_seconds,
        )

    def start(self, request: MaaRunRequest) -> LiveRun:
        profile_data = self._profile_data(request.profile)
        resources = maa_run_resources_from_profile(profile_data)
        run_id = uuid.uuid4().hex[:12]
        log_files = self.diagnostics.stream_log_files("maa-cli", run_id)
        max_retries = _retry_count(request.retry_count)
        log_profile = _maa_cli_log_profile(self.diagnostics)
        task_data = load_task_file(resolve_task_file(self.runtime, request.task))
        policies = task_policies_from_config(task_data)
        selected_task_ids = enabled_task_ids_from_config(task_data)
        callbacks = ManualMaaRunCallbacks(
            runtime=self.runtime,
            diagnostics=self.diagnostics,
            request=request,
            policies=policies,
            selected_task_ids=selected_task_ids,
        )
        state = self.runs.start(
            RunStartPlan(
                kind="manual",
                title=request.task,
                callbacks=callbacks.to_callbacks(),
                max_retries=max_retries,
                timeouts=self.framework_settings.run_timeouts(),
                log_profile=log_profile,
                metadata={
                    "task": request.task,
                    "profile": request.profile,
                    "log_level": request.log_level,
                    "resource_locks": [resource.to_dict() for resource in resources],
                    "run_priority": RUN_PRIORITY_NORMAL,
                },
                log_files=log_files,
                event_log_file=self.diagnostics.event_log_file(run_id),
                initial_attempt_payload={"task_ids": selected_task_ids},
                history_scope=("manual",),
                resources=resources,
                priority_name="normal",
                force_after_seconds=self._preemption_force_after_seconds(),
                text=RunTextTemplates(
                    process_name="maa-cli",
                    completed="",
                    exit_code="maa-cli 退出码: {return_code}",
                    retry_start="第 {retry_index} 次重试",
                    retry_next="",
                    retry_limit_reached="",
                    start_failed="启动 maa-cli 失败: {error}",
                    stop_requested="收到停止请求，正在等待 maa-cli 自行停止...",
                    force_stop_requested="收到强制停止请求，正在强杀 maa-cli...",
                    execution_failed="手动运行失败: {error}",
                ),
            ),
            run_id=run_id,
        )
        logger.info("manual run started run_id=%s task=%s profile=%s log_level=%s", run_id, request.task, request.profile, request.log_level)
        return state

    def wait_for_change(self, last_version: int, timeout: float | None = None) -> int:
        return self.runs.wait_for_change(last_version, timeout)

    def current(self) -> LiveRun | None:
        return self.runs.current()

    def current_response(self, *, include_logs: bool = True) -> dict[str, object]:
        return self.runs.current_response(include_logs=include_logs)

    def get(self, run_id: str) -> LiveRun | None:
        return self.runs.get(run_id)

    def stop_current(self) -> LiveRun:
        return self.runs.stop_current()

    def force_stop_current(self) -> LiveRun:
        return self.runs.force_stop_current()

    def stop(self, run_id: str) -> LiveRun:
        return self.runs.stop(run_id)

    def force_stop(self, run_id: str) -> LiveRun:
        return self.runs.force_stop(run_id)

    def _preemption_force_after_seconds(self) -> float | None:
        seconds = self.framework_settings.run_timeouts().stop_kill_seconds
        return float(seconds) if seconds > 0 else None

    def _profile_data(self, profile: str) -> dict[str, object]:
        try:
            data = self.configs.read_profile_config(profile).get("data")
        except (FileNotFoundError, ValueError):
            return {}
        return dict_value(data)


def _maa_cli_log_profile(diagnostics: Diagnostics) -> RunLogProfile:
    return RunLogProfile(
        max_output_chunks=2000,
        register_sources=register_maa_log_sources,
        source_for_stream=lambda stream: f"maa-cli:{stream}",
        diagnostic_sink=diagnostics.stream_sink("maa-cli"),
    )


def _generated_config_dir(runtime: MaaRuntime, run_id: str) -> str:
    return runtime.path_references.reference("runtime", runtime.generated_config_dir / run_id)


def maacore_log_source(runtime: MaaRuntime) -> Path:
    return runtime.state_home / "maa" / "debug" / "asst.log"


def current_log_offset(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


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


def _attempt_task_ids(attempt: RunAttempt) -> list[str]:
    return _payload_task_ids(attempt.payload)


def _payload_task_ids(payload: dict[str, object]) -> list[str]:
    value = payload.get("task_ids")
    return [str(item) for item in value] if isinstance(value, list) else []


def _task_names(policy_by_id: dict[str, TaskPolicy], task_ids: list[str]) -> list[str]:
    return [policy_by_id[task_id].name if task_id in policy_by_id else task_id for task_id in task_ids]
