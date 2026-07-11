from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from maa_auto_panel.config.app_settings import FrameworkSettingsManager
from maa_auto_panel.config.manager import ConfigManager
from maa_auto_panel.diagnostics import Diagnostics, get_logger
from maa_auto_panel.logs.pipeline import LogSourceSpec, plain_translate_line
from maa_auto_panel.logs.pipeline import default_tone_for_source
from maa_auto_panel.logs.state import RunLogBuffer
from maa_auto_panel.maa.log_templates import register_maa_log_sources
from maa_auto_panel.maa.results import MaaTaskDescriptor, MaaTaskResultCollector
from maa_auto_panel.maa.runner import load_task_file, prepare_maa_cli_task, resolve_task_file
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.process import StreamingProcessResult
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.coordinator import RunCoordinator
from maa_auto_panel.run_manager.logs import RunLogProfile
from maa_auto_panel.run_manager.manager import (
    GenericRunManager,
    RetryDecision,
    RunAttempt,
    RunCallbacks,
    RunScriptHooks,
    RunScriptSpec,
    RunStartPlan,
    RunTextTemplates,
)
from maa_auto_panel.run_manager.state import LiveRun, RunTimeouts
from maa_auto_panel.run_manager.store import RunStateStore, StoredRun
from maa_auto_panel.run_resources import adb_device_resources_from_profile, schedule_priority
from maa_auto_panel.scheduler.config import ScheduleConfigManager
from maa_auto_panel.scheduler.models import DailyTaskStats, ScheduleConfig, ScheduleEntry, TaskPolicy
from maa_auto_panel.scheduler.policy import initial_task_selection, remaining_enabled_slots, retry_task_ids, task_policies_from_config
from maa_auto_panel.scheduler.scripts import ScheduleScriptManager
from maa_auto_panel.scheduler.state import SchedulerStateStore
from maa_auto_panel.scheduler.time import effective_timezone, extract_client_type, game_day_info, game_day_key, sort_entries_for_game_day
from maa_auto_panel.state import idle_response
from maa_auto_panel.utils import relative_path


logger = get_logger(__name__)


ScheduleRunState = LiveRun


@dataclass
class ScheduledMaaRunCallbacks:
    """Scheduled MAA attempt hooks; GenericRunManager owns lifecycle and retry loop."""

    runtime: MaaRuntime
    scheduler_state: SchedulerStateStore
    diagnostics: Diagnostics
    config: ScheduleConfig
    entry: ScheduleEntry
    client: str
    timezone_name: str
    selected_task_ids: list[str]
    skipped_tasks: list[dict[str, str]]
    policies: list[TaskPolicy]
    sorted_entries: list[ScheduleEntry]

    def __post_init__(self) -> None:
        self.policy_by_id = {policy.id: policy for policy in self.policies}
        self.run_successful_task_ids: set[str] = set()
        self.collectors: dict[str, MaaTaskResultCollector] = {}
        self.maacore_offsets: dict[str, int] = {}

    def to_callbacks(self) -> RunCallbacks:
        return RunCallbacks(
            on_start=self.on_start,
            before_retry=self.before_retry,
            build_command=self.build_command,
            on_raw_line=self.on_raw_line,
            evaluate_attempt=self.evaluate_attempt,
            after_attempt=self.after_attempt,
        )

    def on_start(self, attempt: RunAttempt) -> RetryDecision | None:
        selected = list(self.selected_task_ids)
        if not selected:
            attempt.add_event("本次没有需要运行的子任务。", tone="info")
            self._append_skip_events(attempt, self.skipped_tasks)
            return RetryDecision(
                "skipped",
                0,
                run_status="skipped",
                retry_metadata={"task_results": []},
                summary_patch={"reason": "no-selected-tasks"},
            )

        attempt.add_event(f"本次运行实际任务: {', '.join(_task_names(self.policy_by_id, selected))}", tone="info")
        self._append_skip_events(attempt, self.skipped_tasks)
        return None

    def before_retry(self, attempt: RunAttempt, previous_decision: RetryDecision) -> None:
        if not previous_decision.continue_retry or attempt.stop_requested:
            return
        every = self.config.retry.buffer_every_retries
        seconds = self.config.retry.buffer_seconds
        completed_attempts = attempt.attempt_index - 1
        if every <= 0 or seconds <= 0 or completed_attempts % every != 0:
            return
        attempt.add_event(f"已连续重试 {completed_attempts} 次，缓冲等待 {seconds}s。", tone="warning")
        attempt.wait_for_stop(seconds)

    def build_command(self, attempt: RunAttempt) -> CommandSpec:
        task_ids = _attempt_task_ids(attempt)
        prepare_messages: list[str] = []
        generated_profile = self.config.profile_name or f"{self.config.id}-profile"
        generated_run_id = f"schedule-{attempt.run_id}"
        run_task, run_env = prepare_maa_cli_task(
            self.runtime,
            self.config.task_config,
            run_id=generated_run_id,
            attempt=attempt.attempt_index,
            messages=prepare_messages,
            selected_task_ids=set(task_ids),
            force_enable_selected=True,
            profile_data=self.config.profile_data,
            profile_name=generated_profile,
        )
        cmd = [
            str(self.runtime.maa_bin),
            "run",
            run_task,
            "--batch",
            "--profile",
            generated_profile,
        ]
        if self.config.log_level > 0:
            cmd.extend(["-v"] * self.config.log_level)

        attempt.add_event(f"开始第 {attempt.attempt_index} 次尝试: {', '.join(_task_names(self.policy_by_id, task_ids))}", tone="info")
        for message in prepare_messages:
            attempt.add_event(message, tone="info")
        task_descriptors = _task_descriptors(self.policy_by_id, task_ids)
        attempt.configure_log(lambda log: log.begin_task_sequence(_task_descriptor_dicts(task_descriptors)))
        self.collectors[attempt.retry_id] = MaaTaskResultCollector(task_descriptors)
        self.maacore_offsets[attempt.retry_id] = self.diagnostics.maacore_log_offset()
        return CommandSpec(cmd, env=run_env)

    def on_raw_line(self, attempt: RunAttempt, stream: str, line: str) -> None:
        collector = self.collectors.get(attempt.retry_id)
        if collector is not None:
            collector.consume_raw_line(f"maa-cli:{stream}", line)

    def evaluate_attempt(self, attempt: RunAttempt, result: StreamingProcessResult) -> RetryDecision:
        local_tz = effective_timezone(self.timezone_name)
        collector = self.collectors.pop(attempt.retry_id, MaaTaskResultCollector([]))
        collector.finish()
        task_results = list(collector.results)
        task_ids = _attempt_task_ids(attempt)
        status_by_task_id = collector.status_by_task_id(task_ids)
        attempt_status = "succeeded" if result.return_code == 0 and all(status == "succeeded" for status in status_by_task_id.values()) else "failed"
        if result.stopped or attempt.stop_requested:
            attempt_status = "stopped"
        if result.timed_out:
            attempt_status = "failed"
        maacore_log_file = self.diagnostics.capture_maacore_log(attempt.retry_id, self.maacore_offsets.pop(attempt.retry_id, 0))
        current_game_day = game_day_key(datetime.now(local_tz), client=self.client)
        counted_statuses = {task_id: status for task_id, status in status_by_task_id.items() if status != "missing"}
        self.run_successful_task_ids.update(task_id for task_id, status in counted_statuses.items() if status == "succeeded")
        self.scheduler_state.update_daily_stats(
            schedule_id=self.config.id,
            game_day=current_game_day,
            task_names={task_id: self.policy_by_id[task_id].name for task_id in counted_statuses if task_id in self.policy_by_id},
            task_statuses=counted_statuses,
        )
        stats = self.scheduler_state.daily_stats(self.config.id, current_game_day)
        next_task_ids: list[str] = []
        if attempt_status != "stopped":
            next_task_ids = retry_task_ids(
                self.policies,
                self.entry,
                self.sorted_entries,
                stats,
                status_by_task_id,
                run_successful_task_ids=self.run_successful_task_ids,
            )
        will_retry = bool(next_task_ids) and attempt.attempt_index < attempt.max_retries and attempt_status != "stopped"
        final_status = None
        if attempt_status == "stopped":
            final_status = "stopped"
        elif not next_task_ids:
            final_status = _final_status(
                self.policies,
                self.entry,
                self.sorted_entries,
                stats,
                status_by_task_id,
                self.run_successful_task_ids,
            )
        elif not will_retry:
            final_status = "failed"

        summary = {}
        if final_status is not None:
            summary = {
                "final_status": final_status,
                "retries": attempt.attempt_index,
                "retry_groups": 1,
            }
        return RetryDecision(
            attempt_status,
            result.return_code,
            run_status=final_status,
            continue_retry=will_retry,
            next_attempt_payload={"task_ids": next_task_ids},
            retry_metadata={"task_ids": task_ids, "task_results": task_results},
            retry_artifacts={
                "generated_config_dir": relative_path(self.runtime.generated_config_dir / f"schedule-{attempt.run_id}", self.runtime.data_root),
                "maacore_log_file": maacore_log_file,
            },
            summary_patch=summary,
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

    def _append_skip_events(
        self,
        attempt: RunAttempt,
        skipped: list[dict[str, str]],
    ) -> None:
        enabled = set(self.entry.task_ids)
        for item in skipped:
            task_id = item.get("task_id", "")
            if task_id not in enabled:
                continue
            task_name = self.policy_by_id[task_id].name if task_id in self.policy_by_id else task_id
            attempt.add_event(f"跳过子任务: {task_name}，原因: {item.get('reason', '未说明')}", tone="info")


class SchedulerService:
    """Background scheduler: checks enabled schedules, triggers runs, manages retries and state."""
    def __init__(
        self,
        runtime: MaaRuntime,
        configs: ConfigManager,
        framework_settings: FrameworkSettingsManager,
        schedules: ScheduleConfigManager,
        run_state: RunStateStore | None = None,
        scheduler_state: SchedulerStateStore | None = None,
        diagnostics: Diagnostics | None = None,
        run_coordinator: RunCoordinator | None = None,
    ) -> None:
        self.runtime = runtime
        self.configs = configs
        self.framework_settings = framework_settings
        self.schedules = schedules
        self.store = run_state or RunStateStore(runtime)
        self.scheduler_state = scheduler_state or SchedulerStateStore(runtime)
        self.diagnostics = diagnostics or Diagnostics(runtime)
        self.run_coordinator = run_coordinator or RunCoordinator()
        self.scripts = ScheduleScriptManager(runtime)
        self.runs = GenericRunManager(runtime, self.store, self.diagnostics, self.run_coordinator)
        self._shutdown = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._shutdown.is_set():
                raise RuntimeError("Scheduler is shutting down")
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._loop, name="maa-scheduler", daemon=False)
            self._thread.start()

    def begin_shutdown(self) -> None:
        self._shutdown.set()

    def join_until(self, deadline: float) -> bool:
        with self._lifecycle_lock:
            thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
        return not thread.is_alive()

    def status(self) -> dict[str, object]:
        settings = self.framework_settings.read()
        scheduler_settings = _nested(settings.get("data"), ["framework", "scheduler"])
        enabled = bool(scheduler_settings.get("enabled")) if isinstance(scheduler_settings, dict) else False
        return {
            "enabled": enabled,
            "status": "running" if enabled else "disabled",
            "current_run": self.current_response(include_logs=False),
            "recent_runs": [run.to_dict() for run in self.store.runs(kind="schedule", limit=8)],
        }

    def list_schedules(self) -> dict[str, object]:
        files = self.schedules.list_files()
        recent = self.store.runs(kind="schedule", limit=50)
        last_by_schedule: dict[str, dict[str, object]] = {}
        for run in recent:
            schedule_id = str(run.metadata.get("schedule_id") or "")
            if schedule_id:
                last_by_schedule.setdefault(schedule_id, run.to_dict())
        return {
            "status": self.status(),
            "schedules": [
                {
                    **item.to_dict(),
                    "last_run": last_by_schedule.get(item.id),
                }
                for item in files
            ],
        }

    def read_schedule(self, schedule_id: str) -> dict[str, object]:
        config = self.schedules.read(schedule_id)
        return self._schedule_response(config)

    def create_schedule(self, name: str, task_config: str | None = None) -> dict[str, object]:
        configs = self.configs.list_kind("tasks")
        selected_task_config = task_config or (configs[0].name if configs else "")
        if not selected_task_config:
            raise ValueError("No task config available")
        task_response = self.configs.read_task_config(selected_task_config)
        task_ids = [str(item.get("id")) for item in task_response.get("task_items", []) if isinstance(item, dict) and item.get("id")]
        profile = self.configs.read_profile_config("default")
        config = self.schedules.create_default(
            name=name,
            task_config=selected_task_config,
            default_profile=profile.get("data") if isinstance(profile.get("data"), dict) else {},
            task_ids=task_ids,
        )
        logger.info("schedule created schedule_id=%s name=%s task_config=%s", config.id, name, selected_task_config)
        return self._schedule_response(config)

    def save_schedule(self, schedule_id: str, payload: dict[str, Any]) -> dict[str, object]:
        task_config = str(payload.get("task_config") or "")
        if task_config:
            self.configs.resolve("tasks", task_config)
        profile = payload.get("profile")
        if isinstance(profile, dict):
            validation = self.configs.schema_validator.validate_profile_config(profile)
            if not validation.valid:
                from maa_auto_panel.config.manager import ConfigValidationFailure

                raise ConfigValidationFailure(validation)
        config = self.schedules.write(schedule_id, payload)
        logger.info("schedule saved schedule_id=%s", schedule_id)
        return self._schedule_response(config)

    def delete_schedule(self, schedule_id: str) -> dict[str, object]:
        logger.warning("schedule deleted schedule_id=%s", schedule_id)
        return {"deleted": self.schedules.delete(schedule_id).to_dict()}

    def start_now(self, schedule_id: str, entry_id: str | None = None, *, retry_count: int | None = None) -> ScheduleRunState:
        config = self.schedules.read(schedule_id)
        entry = next((item for item in config.entries if item.id == entry_id), None) if entry_id else None
        entry = entry or config.entries[0]
        return self._start_run(config, entry, trigger="manual", retry_count=retry_count)

    def current(self) -> ScheduleRunState | None:
        return self.runs.current()

    def current_response(self, schedule_id: str | None = None, *, include_logs: bool = True) -> dict[str, object]:
        payload = self.runs.current_response(include_logs=include_logs)
        version = payload.get("stream_version", 0)
        run = payload.get("run")
        metadata = run.get("metadata") if isinstance(run, dict) else None
        current_schedule_id = metadata.get("schedule_id") if isinstance(metadata, dict) else None
        if schedule_id is not None and current_schedule_id != schedule_id:
            payload = idle_response()
        payload["stream_version"] = version
        return payload

    def wait_for_change(self, last_version: int, timeout: float | None = None) -> int:
        return self.runs.wait_for_change(last_version, timeout)

    def stop_current(self) -> ScheduleRunState:
        return self.runs.stop_current()

    def force_stop_current(self) -> ScheduleRunState:
        return self.runs.force_stop_current()

    def _schedule_response(self, config: ScheduleConfig) -> dict[str, object]:
        task_config_data = self.configs.read_task_config(config.task_config)
        task_data = task_config_data.get("data") if isinstance(task_config_data.get("data"), dict) else {}
        client = extract_client_type(task_data)
        timezone_name = str(self.framework_settings.read()["effective_timezone"]["name"])
        timeline = game_day_info(config.entries, client=client, timezone_name=timezone_name)
        sorted_entries = sort_entries_for_game_day(config.entries, client=client, local_tz=effective_timezone(timezone_name))
        return {
            "file": self.schedules.file_info(config).to_dict(),
            "config": config.to_dict(),
            "task_config": task_config_data,
            "task_policies": [policy.to_dict() for policy in task_policies_from_config(task_data)],
            "timeline": {
                **timeline.to_dict(),
                "entries": [entry.to_dict() for entry in sorted_entries],
            },
            "daily_stats": {
                key: value.to_dict()
                for key, value in self.scheduler_state.daily_stats(config.id, timeline.game_day).items()
            },
            "recent_runs": [run.to_dict() for run in self._recent_schedule_runs(config.id, limit=12)],
            "scripts": [script.to_dict() for script in self.scripts.list_scripts()],
            "current_run": self.current_response(config.id, include_logs=False),
        }

    def _recent_schedule_runs(self, schedule_id: str, *, limit: int) -> list[StoredRun]:
        runs = [
            run
            for run in self.store.runs(kind="schedule", limit=0)
            if run.metadata.get("schedule_id") == schedule_id
        ]
        return runs[:limit]

    def _loop(self) -> None:
        while not self._shutdown.wait(15):
            try:
                if not _scheduler_enabled(self.framework_settings):
                    continue
                self._start_due_entries()
            except Exception:
                logger.exception("scheduler loop failed")
                continue

    def _start_due_entries(self) -> None:
        settings = self.framework_settings.read()
        timezone_name = str(settings["effective_timezone"]["name"])
        local_tz = effective_timezone(timezone_name)
        now = datetime.now(local_tz)
        current_time = now.strftime("%H:%M")
        for file_info in self.schedules.list_files():
            config = self.schedules.read(file_info.id)
            if not config.enabled:
                continue
            task_data = load_task_file(resolve_task_file(self.runtime, config.task_config))
            client = extract_client_type(task_data)
            current_game_day = game_day_key(now, client=client)
            for entry in config.entries:
                if not entry.enabled or entry.time != current_time:
                    continue
                if self.scheduler_state.already_triggered(schedule_id=config.id, entry_id=entry.id, game_day=current_game_day):
                    continue
                try:
                    state = self._start_run(config, entry, trigger="schedule")
                except RuntimeError as exc:
                    logger.info("scheduled due entry deferred schedule_id=%s entry_id=%s reason=%s", config.id, entry.id, exc)
                    return
                self.scheduler_state.mark_triggered(schedule_id=config.id, entry_id=entry.id, game_day=current_game_day, run_id=state.id)
                return

    def _start_run(self, config: ScheduleConfig, entry: ScheduleEntry, *, trigger: str, retry_count: int | None = None) -> ScheduleRunState:
        task_data = load_task_file(resolve_task_file(self.runtime, config.task_config))
        client = extract_client_type(task_data)
        timezone_name = str(self.framework_settings.read()["effective_timezone"]["name"])
        local_tz = effective_timezone(timezone_name)
        game_day = game_day_key(datetime.now(local_tz), client=client)
        sorted_entries = sort_entries_for_game_day(config.entries, client=client, local_tz=local_tz)
        policies = task_policies_from_config(task_data)
        stats = self.scheduler_state.daily_stats(config.id, game_day)
        selection = initial_task_selection(policies, entry, stats)
        run_id = uuid.uuid4().hex[:12]
        log_files = self.diagnostics.maa_cli_log_files(run_id)
        if config.restart.script:
            log_files.update(self.diagnostics.script_log_files(run_id))
        max_retries = _retry_count(retry_count if retry_count is not None else config.retry.max_retries)
        priority = schedule_priority(trigger)
        resources = adb_device_resources_from_profile(config.profile_data)
        log_profile = _schedule_log_profile(self.diagnostics, include_script=bool(config.restart.script))
        script_log_profile = _schedule_script_log_profile(self.diagnostics)
        callbacks = ScheduledMaaRunCallbacks(
            runtime=self.runtime,
            scheduler_state=self.scheduler_state,
            diagnostics=self.diagnostics,
            config=config,
            entry=entry,
            client=client,
            timezone_name=timezone_name,
            selected_task_ids=selection.selected,
            skipped_tasks=selection.skipped,
            policies=policies,
            sorted_entries=sorted_entries,
        )
        state = self.runs.start(
            RunStartPlan(
                kind="schedule",
                title=f"{config.name} / {entry.name}",
                callbacks=callbacks.to_callbacks(),
                max_retries=max_retries,
                timeouts=config.timeouts.to_run_timeouts(),
                log_profile=log_profile,
                script_hooks=_restart_script_hooks(self.scripts, config, script_log_profile),
                script_log_profile=script_log_profile,
                metadata={
                    "schedule_id": config.id,
                    "schedule_name": config.name,
                    "entry_id": entry.id,
                    "entry_name": entry.name,
                    "task_config": config.task_config,
                    "profile": config.profile_name,
                    "profile_name": config.profile_name,
                    "log_level": config.log_level,
                    "game_day": game_day,
                    "trigger": trigger,
                    "resource_locks": [resource.to_dict() for resource in resources],
                    "run_priority": priority,
                },
                log_files=log_files,
                event_log_file=self.diagnostics.event_log_file(run_id),
                initial_attempt_payload={"task_ids": selection.selected},
                history_scope=("schedules", config.id),
                resources=resources,
                priority_name="schedule.auto" if trigger == "schedule" else "schedule.manual",
                force_after_seconds=float(config.timeouts.stop_kill_seconds) if config.timeouts.stop_kill_seconds > 0 else None,
                text=RunTextTemplates(
                    process_name="maa-cli",
                    start="",
                    completed="",
                    exit_code="maa-cli 退出码: {return_code}",
                    retry_start="第 {retry_index} 次重试",
                    retry_next="",
                    retry_limit_reached="",
                    start_failed="启动 maa-cli 失败: {error}",
                    stop_requested="收到停止请求，正在终止 maa-cli...",
                    force_stop_requested="收到强制停止请求，正在强制停止 maa-cli...",
                    execution_failed="定时运行失败: {error}",
                ),
            ),
            run_id=run_id,
        )
        logger.info("scheduled run started run_id=%s schedule_id=%s entry_id=%s trigger=%s", run_id, config.id, entry.id, trigger)
        return state


def _restart_script_hooks(
    scripts: ScheduleScriptManager,
    config: ScheduleConfig,
    script_log_profile: RunLogProfile,
) -> RunScriptHooks:
    if not config.restart.script or config.restart.mode not in {"before_run", "before_retry"}:
        return RunScriptHooks()

    def command(_attempt: RunAttempt) -> CommandSpec:
        script_command = scripts.command(config.restart.script, config.restart.variables)
        return CommandSpec(script_command.cmd, env=script_command.env)

    spec = RunScriptSpec(
        command=command,
        label=config.restart.script,
        source_prefix="script",
        timeouts=RunTimeouts(runtime_kill_seconds=120),
        log_profile=script_log_profile,
    )
    if config.restart.mode == "before_run":
        return RunScriptHooks(before_run=(spec,))
    return RunScriptHooks(before_retry=(spec,))


def _scheduler_enabled(settings: FrameworkSettingsManager) -> bool:
    data = settings.read().get("data")
    scheduler = _nested(data, ["framework", "scheduler"])
    return bool(scheduler.get("enabled")) if isinstance(scheduler, dict) else False


def _nested(data: object, path: list[str]) -> dict[str, Any]:
    current: object = data
    for key in path:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _task_names(policy_by_id: dict[str, TaskPolicy], task_ids: list[str]) -> list[str]:
    return [policy_by_id[task_id].name if task_id in policy_by_id else task_id for task_id in task_ids]


def _attempt_task_ids(attempt: RunAttempt) -> list[str]:
    return _payload_task_ids(attempt.payload)


def _payload_task_ids(payload: dict[str, object]) -> list[str]:
    value = payload.get("task_ids")
    return [str(item) for item in value] if isinstance(value, list) else []


def _task_descriptors(policy_by_id: dict[str, TaskPolicy], task_ids: list[str]) -> list[MaaTaskDescriptor]:
    return [
        MaaTaskDescriptor(task_id=task_id, source_name=policy_by_id[task_id].type, name=policy_by_id[task_id].name)
        for task_id in task_ids
        if task_id in policy_by_id
    ]


def _task_descriptor_dicts(descriptors: list[MaaTaskDescriptor]) -> list[dict[str, str]]:
    return [{"task_id": item.task_id, "source_name": item.source_name, "name": item.name} for item in descriptors]


def _register_schedule_log_sources(log: RunLogBuffer, *, include_script: bool) -> None:
    register_maa_log_sources(log)
    if include_script:
        hooks = ("before_run", "after_run", "before_retry", "after_retry")
        for source in (f"script:{hook}:{stream}" for hook in hooks for stream in ("stdout", "stderr")):
            log.register_source(LogSourceSpec(source, default_tone_for_source(source), plain_translate_line))


def _schedule_log_profile(diagnostics: Diagnostics, *, include_script: bool) -> RunLogProfile:
    return RunLogProfile(
        max_output_chunks=3000,
        register_sources=lambda log: _register_schedule_log_sources(log, include_script=include_script),
        source_for_stream=lambda stream: f"maa-cli:{stream}",
        diagnostic_sink=diagnostics.append_maa_cli_output,
    )


def _schedule_script_log_profile(diagnostics: Diagnostics) -> RunLogProfile:
    return RunLogProfile(
        max_output_chunks=3000,
        source_for_stream=lambda stream: f"script:{stream}",
        diagnostic_sink=diagnostics.append_script_output,
    )


def _final_status(
    policies: list[TaskPolicy],
    entry: ScheduleEntry,
    sorted_entries: list[ScheduleEntry],
    stats: dict[str, DailyTaskStats],
    last_statuses: dict[str, str],
    run_successful_task_ids: set[str],
) -> str:
    enabled = set(entry.task_ids)
    soft_failed = False
    for policy in policies:
        if policy.id not in enabled:
            continue
        task_stats = stats.get(policy.id, DailyTaskStats(task_id=policy.id, task_name=policy.name))
        if policy.important:
            if policy.unlimited_runs:
                if policy.id not in run_successful_task_ids:
                    return "failed"
            elif task_stats.successes < policy.min_daily_successes and policy.id not in run_successful_task_ids:
                remaining_successes = max(0, policy.min_daily_successes - task_stats.successes)
                remaining_slots = remaining_enabled_slots(sorted_entries, current_entry_id=entry.id, task_id=policy.id)
                if remaining_slots <= remaining_successes:
                    return "failed"
            continue
        if last_statuses.get(policy.id) not in {"succeeded", None}:
            soft_failed = True
    return "soft_failed" if soft_failed else "succeeded"


def _retry_count(value: object) -> int:
    try:
        return min(50, max(1, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1
