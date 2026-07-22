from __future__ import annotations

import uuid
from dataclasses import dataclass

from maa_auto_panel.config.app_settings import FrameworkSettingsManager
from maa_auto_panel.config.manager import ConfigManager
from maa_auto_panel.diagnostics import Diagnostics, get_logger
from maa_auto_panel.maa.log_templates import configure_maa_log_template, maa_log_source_specs
from maa_auto_panel.maa.results import MaaTaskDescriptor, retry_result_summary
from maa_auto_panel.maa.retry import MaaRetrySession, load_task_file, resolve_task_file
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.notifications import NotificationService
from maa_auto_panel.process import StreamingProcessResult
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.contracts import RetryDecision, RunCallbacks, RunStartPlan, RunTextTemplates
from maa_auto_panel.run_manager.coordinator import RunCoordinator
from maa_auto_panel.run_manager.context import RetryContext
from maa_auto_panel.run_manager.logs import RunLogProfile
from maa_auto_panel.run_manager.manager import GenericRunManager
from maa_auto_panel.run_manager.state import LiveRun
from maa_auto_panel.run_manager.store import RunStateStore
from maa_auto_panel.run_resources import RUN_PRIORITY_NORMAL, maa_run_resources_from_profile
from maa_auto_panel.scheduler.models import TaskPolicy
from maa_auto_panel.scheduler.policy import enabled_task_ids_from_config, retry_unfinished_task_ids, task_policies_from_config
from maa_auto_panel.utils import dict_value


logger = get_logger(__name__)


@dataclass(frozen=True)
class MaaRunRequest:
    """Immutable request: which task and profile to run, at what log level."""
    task: str
    profile: str = "default"
    log_level: int = 1
    retry_count: int = 1


@dataclass
class ManualMaaRunCallbacks:
    """Manual retry policy around the shared MAA retry translation session."""

    maa: MaaRetrySession
    policies: list[TaskPolicy]
    selected_task_ids: list[str]

    def __post_init__(self) -> None:
        self.policy_by_id = {policy.id: policy for policy in self.policies}
        self.run_successful_task_ids: set[str] = set()

    def to_callbacks(self) -> RunCallbacks:
        return RunCallbacks(
            on_start=self.on_start,
            build_command=self.build_command,
            on_raw_line=self.on_raw_line,
            evaluate_retry=self.evaluate_retry,
            after_retry=self.after_retry,
        )

    def on_start(self, context: RetryContext) -> RetryDecision | None:
        if self.selected_task_ids:
            return None
        context.add_event("当前任务配置没有启用的子任务。", tone="warning")
        return RetryDecision(
            "skipped",
            0,
            run_status="skipped",
            retry_metadata={"task_results": []},
            retry_artifacts={"generated_config_dir": self.maa.generated_config_dir},
            summary_patch={"task_results": [], "generated_config_dir": self.maa.generated_config_dir},
        )

    def build_command(self, context: RetryContext) -> CommandSpec:
        task_ids = _retry_task_ids(context)
        task_descriptors = _task_descriptors(self.policy_by_id, task_ids)
        return self.maa.prepare_retry(context, task_descriptors)

    def on_raw_line(self, context: RetryContext, stream: str, line: str) -> None:
        self.maa.consume_raw_line(context, stream, line)

    def evaluate_retry(self, context: RetryContext, result: StreamingProcessResult) -> RetryDecision:
        task_ids = _retry_task_ids(context)
        outcome = self.maa.finish_retry(context, task_ids)
        task_results = outcome.task_results
        status_by_task_id = outcome.status_by_task_id
        self.run_successful_task_ids.update(task_id for task_id, status in status_by_task_id.items() if status == "succeeded")

        retry_status = "succeeded" if result.return_code == 0 and all(status == "succeeded" for status in status_by_task_id.values()) else "failed"
        if result.stopped or context.stop_requested:
            retry_status = "stopped"
        if result.timed_out:
            retry_status = "failed"

        next_task_ids: list[str] = []
        if retry_status != "stopped":
            next_task_ids = retry_unfinished_task_ids(
                self.selected_task_ids,
                status_by_task_id,
                run_successful_task_ids=self.run_successful_task_ids,
            )
        will_retry = bool(next_task_ids) and context.retry_index < context.max_retries and retry_status != "stopped"
        run_status = None
        if retry_status == "stopped":
            run_status = "stopped"
        elif not next_task_ids:
            run_status = "succeeded"
        elif not will_retry:
            run_status = "failed"

        return RetryDecision(
            retry_status,
            result.return_code,
            run_status=run_status,
            continue_retry=will_retry,
            next_retry_payload={"task_ids": next_task_ids},
            retry_metadata={"task_ids": task_ids, "task_results": task_results},
            retry_artifacts={"generated_config_dir": outcome.generated_config_dir, "diagnostic_log_file": outcome.diagnostic_log_file},
            retry_summary_messages=retry_result_summary(
                _task_descriptors(self.policy_by_id, self.selected_task_ids),
                task_results,
                planned_task_ids=task_ids,
                retry_status=retry_status,
            ),
            summary_patch={"task_results": task_results, "generated_config_dir": outcome.generated_config_dir},
        )

    def after_retry(
        self,
        context: RetryContext,
        _result: StreamingProcessResult,
        decision: RetryDecision,
    ) -> RetryDecision | None:
        if context.stop_requested or decision.retry_status == "stopped":
            return None
        next_task_ids = _payload_task_ids(decision.next_retry_payload or {})
        if decision.continue_retry and next_task_ids:
            context.add_event(f"准备重试: {', '.join(_task_names(self.policy_by_id, next_task_ids))}", tone="warning")
        elif next_task_ids and context.retry_index >= context.max_retries:
            context.add_event("重试次数已达上限，仍有未成功子任务。", tone="danger")
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
        log_files = self.diagnostics.stream_log_files(("maa", "maa-cli"), run_id)
        max_retries = _retry_count(request.retry_count)
        log_profile = _maa_cli_log_profile(self.diagnostics)
        task_data = load_task_file(resolve_task_file(self.runtime, request.task))
        policies = task_policies_from_config(task_data)
        selected_task_ids = enabled_task_ids_from_config(task_data)
        callbacks = ManualMaaRunCallbacks(
            maa=MaaRetrySession(
                self.runtime,
                self.diagnostics,
                task=request.task,
                profile_name=request.profile,
                log_level=request.log_level,
                generated_run_id=run_id,
            ),
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
                initial_retry_payload={"task_ids": selected_task_ids},
                history_scope=("manual",),
                resources=resources,
                priority_name="normal",
                force_after_seconds=self._preemption_force_after_seconds(),
                text=RunTextTemplates(
                    process_name="maa-cli",
                    completed="",
                    exit_code="maa-cli 退出码: {return_code}",
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
        source_specs=maa_log_source_specs(),
        configure_buffer=configure_maa_log_template,
        source_for_stream=lambda stream: f"maa-cli:{stream}",
        diagnostic_sink=diagnostics.stream_sink(("maa", "maa-cli")),
    )


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


def _retry_task_ids(context: RetryContext) -> list[str]:
    return _payload_task_ids(context.payload)


def _payload_task_ids(payload: dict[str, object]) -> list[str]:
    value = payload.get("task_ids")
    return [str(item) for item in value] if isinstance(value, list) else []


def _task_names(policy_by_id: dict[str, TaskPolicy], task_ids: list[str]) -> list[str]:
    return [policy_by_id[task_id].name if task_id in policy_by_id else task_id for task_id in task_ids]
