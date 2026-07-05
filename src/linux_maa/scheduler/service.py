from __future__ import annotations

import subprocess
import threading
import uuid
from datetime import datetime
from typing import Any

from linux_maa.config.app_settings import FrameworkSettingsManager
from linux_maa.config.manager import ConfigManager
from linux_maa.diagnostics import Diagnostics, get_logger
from linux_maa.logs.pipeline import LogSourceSpec, plain_translate_line
from linux_maa.logs.pipeline import default_tone_for_source
from linux_maa.logs.state import RunLogBuffer
from linux_maa.maa.log_templates import register_maa_log_sources
from linux_maa.maa.results import MaaTaskDescriptor, MaaTaskResultCollector
from linux_maa.maa.runner import load_task_file, prepare_maa_cli_task, resolve_task_file
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.process import run_streaming_process
from linux_maa.run_executor import LiveRetry, LiveRun, now_text
from linux_maa.run_state import RunStateStore
from linux_maa.scheduler.config import ScheduleConfigManager
from linux_maa.scheduler.models import DailyTaskStats, ScheduleConfig, ScheduleEntry, TaskPolicy
from linux_maa.scheduler.policy import initial_task_selection, remaining_enabled_slots, retry_task_ids, task_policies_from_config
from linux_maa.scheduler.scripts import ScheduleScriptManager
from linux_maa.scheduler.time import effective_timezone, extract_client_type, game_day_info, game_day_key, sort_entries_for_game_day
from linux_maa.state import idle_response
from linux_maa.time_utils import server_now_iso
from linux_maa.utils import relative_path


logger = get_logger(__name__)


ScheduleRunState = LiveRun


class SchedulerService:
    """Background scheduler: checks enabled schedules, triggers runs, manages retries and state."""
    def __init__(
        self,
        runtime: MaaRuntime,
        configs: ConfigManager,
        framework_settings: FrameworkSettingsManager,
        schedules: ScheduleConfigManager,
        run_state: RunStateStore | None = None,
        diagnostics: Diagnostics | None = None,
    ) -> None:
        self.runtime = runtime
        self.configs = configs
        self.framework_settings = framework_settings
        self.schedules = schedules
        self.store = run_state or RunStateStore(runtime)
        self.diagnostics = diagnostics or Diagnostics(runtime)
        self.scripts = ScheduleScriptManager(runtime)
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._version = 0
        self._current: ScheduleRunState | None = None
        self._shutdown = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def status(self) -> dict[str, object]:
        settings = self.framework_settings.read()
        scheduler_settings = _nested(settings.get("data"), ["framework", "scheduler"])
        enabled = bool(scheduler_settings.get("enabled")) if isinstance(scheduler_settings, dict) else False
        return {
            "enabled": enabled,
            "status": "running" if enabled else "disabled",
            "current_run": self.current_response(include_logs=False),
            "recent_runs": [run.to_dict() for run in self.store.recent_runs(limit=8)],
        }

    def list_schedules(self) -> dict[str, object]:
        files = self.schedules.list_files()
        recent = self.store.recent_runs(limit=50)
        last_by_schedule: dict[str, dict[str, object]] = {}
        for run in recent:
            last_by_schedule.setdefault(run.schedule_id, run.to_dict())
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
                from linux_maa.config.manager import ConfigValidationFailure

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
        with self._lock:
            return self._current

    def current_response(self, schedule_id: str | None = None, *, include_logs: bool = True) -> dict[str, object]:
        with self._lock:
            current = self._current
            version = self._version
            if current is None or (schedule_id is not None and current.metadata.get("schedule_id") != schedule_id):
                payload = idle_response()
            else:
                payload = current.to_dict(include_logs=include_logs)
        payload["stream_version"] = version
        return payload

    def wait_for_change(self, last_version: int, timeout: float | None = None) -> int:
        with self._condition:
            if self._version == last_version:
                self._condition.wait(timeout)
            return self._version

    def stop_current(self) -> ScheduleRunState:
        with self._lock:
            if self._current is None:
                raise KeyError("no-current-schedule-run")
            if self._current.status not in {"running", "stopping"}:
                return self._current
            self._current.request_stop()
            self.diagnostics.append_run_event(self._current.id, "schedule", "framework", "收到停止请求，正在终止 maa-cli...", tone="warning")
            self._append_framework_event(self._current, "收到停止请求，正在终止 maa-cli...", tone="warning")
            logger.warning("scheduled run stop requested run_id=%s schedule_id=%s", self._current.id, self._current.metadata.get("schedule_id"))
            self._notify_locked()
            return self._current

    def force_stop_current(self) -> ScheduleRunState:
        with self._lock:
            if self._current is None:
                raise KeyError("no-current-schedule-run")
            if self._current.status not in {"running", "stopping"}:
                return self._current
            self._current.request_force_stop()
            self.diagnostics.append_run_event(self._current.id, "schedule", "framework", "收到强制停止请求，正在强杀 maa-cli...", tone="danger")
            self._append_framework_event(self._current, "收到强制停止请求，正在强杀 maa-cli...", tone="danger")
            logger.warning("scheduled run force stop requested run_id=%s schedule_id=%s", self._current.id, self._current.metadata.get("schedule_id"))
            self._notify_locked()
            return self._current

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
                for key, value in self.store.daily_stats(config.id, timeline.game_day).items()
            },
            "recent_runs": [run.to_dict() for run in self.store.recent_runs(config.id, limit=12)],
            "scripts": [script.to_dict() for script in self.scripts.list_scripts()],
            "current_run": self.current_response(config.id, include_logs=False),
        }

    def _loop(self) -> None:
        while not self._shutdown.wait(15):
            try:
                if not _scheduler_enabled(self.framework_settings):
                    continue
                current = self.current()
                if current and current.status in {"running", "stopping"}:
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
                if self.store.already_triggered(schedule_id=config.id, entry_id=entry.id, game_day=current_game_day):
                    continue
                state = self._start_run(config, entry, trigger="schedule")
                self.store.mark_triggered(schedule_id=config.id, entry_id=entry.id, game_day=current_game_day, run_id=state.id)
                return

    def _start_run(self, config: ScheduleConfig, entry: ScheduleEntry, *, trigger: str, retry_count: int | None = None) -> ScheduleRunState:
        with self._lock:
            if self._current and self._current.status in {"running", "stopping"}:
                raise RuntimeError(f"Scheduled run already active: {self._current.id}")

            task_data = load_task_file(resolve_task_file(self.runtime, config.task_config))
            client = extract_client_type(task_data)
            timezone_name = str(self.framework_settings.read()["effective_timezone"]["name"])
            game_day = game_day_key(datetime.now(effective_timezone(timezone_name)), client=client)
            run_id = uuid.uuid4().hex[:12]
            started_at = now_text()
            log_files = self.diagnostics.maa_cli_log_files(run_id)
            if config.restart.script:
                log_files.update(self.diagnostics.script_log_files(run_id))
            max_retries = _retry_count(retry_count if retry_count is not None else config.retry.max_retries)
            state = LiveRun(
                id=run_id,
                kind="schedule",
                title=f"{config.name} / {entry.name}",
                status="running",
                started_at=started_at,
                updated_at=started_at,
                max_retries=max_retries,
                log_files=log_files,
                event_log_file=self.diagnostics.event_log_file(run_id),
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
                    "retry_count": max_retries,
                },
            )
            self._current = state
            self._notify_locked()
            logger.info("scheduled run started run_id=%s schedule_id=%s entry_id=%s trigger=%s", run_id, config.id, entry.id, trigger)

        thread = threading.Thread(target=self._execute_run, args=(state, config, entry), daemon=True)
        state.thread = thread
        thread.start()
        return state

    def _execute_run(self, state: ScheduleRunState, config: ScheduleConfig, entry: ScheduleEntry) -> None:
        task_data = load_task_file(resolve_task_file(self.runtime, config.task_config))
        client = extract_client_type(task_data)
        timezone_name = str(self.framework_settings.read()["effective_timezone"]["name"])
        local_tz = effective_timezone(timezone_name)
        sorted_entries = sort_entries_for_game_day(config.entries, client=client, local_tz=local_tz)
        policies = task_policies_from_config(task_data)
        policy_by_id = {policy.id: policy for policy in policies}
        game_day = str(state.metadata.get("game_day") or "")
        stats = self.store.daily_stats(config.id, game_day)
        selection = initial_task_selection(policies, entry, stats)
        selected = selection.selected
        self.store.create_run(
            run_id=state.id,
            kind="schedule",
            title=f"{config.name} / {entry.name}",
            max_retries=state.max_retries,
            log_files=state.log_files,
            event_log_file=state.event_log_file,
            selected_task_ids=selected,
            metadata={
                "schedule_id": config.id,
                "schedule_name": config.name,
                "entry_id": entry.id,
                "entry_name": entry.name,
                "task_config": config.task_config,
                "game_day": game_day,
                "trigger": str(state.metadata.get("trigger") or ""),
            },
        )

        if not selected:
            self._append_framework_event(state, "本次没有需要运行的子任务。", tone="info")
            self._append_skip_events(state, policy_by_id, selection.skipped, entry)
            retry = state.current_retry
            retry_count = 0
            if retry is not None:
                with self._lock:
                    retry.seal(status="skipped", return_code=0)
                    state.touch()
                    self._notify_locked()
                self.store.add_retry(
                    retry_id=retry.id,
                    run_id=state.id,
                    retry_index=retry.retry_index,
                    retry_group=retry.retry_group,
                    status="skipped",
                    started_at=retry.started_at,
                    updated_at=retry.updated_at,
                    ended_at=retry.ended_at or retry.updated_at,
                    return_code=0,
                    task_ids=[],
                    task_results=retry.task_results,
                    log_entries=retry.log.entries(),
                    log_files=retry.log_files,
                )
                retry_count = 1
            self.store.finish_run(
                state.id,
                status="skipped",
                retry_count=retry_count,
                retry_group_count=retry.retry_group if retry is not None else 0,
                summary={"reason": "no-selected-tasks"},
            )
            self.store.enforce_retention()
            self.diagnostics.enforce_retention()
            self._set_done(state, "skipped", 0)
            return

        self._append_framework_event(state, f"本次运行实际任务: {', '.join(_task_names(policy_by_id, selected))}", tone="info")
        self._append_skip_events(state, policy_by_id, selection.skipped, entry)
        self._run_restart_script(state, config, "before_run")

        attempt_index = 0
        next_task_ids = selected
        final_status = "failed"
        final_return_code: int | None = None
        run_successful_task_ids: set[str] = set()

        while next_task_ids and attempt_index < state.max_retries and not state.stop_requested:
            attempt_index += 1
            if attempt_index > 1:
                self._run_restart_script(state, config, "before_retry")
            attempt_result = self._run_attempt(
                state,
                config,
                task_ids=next_task_ids,
                attempt_index=attempt_index,
                retry_group=1,
                policy_by_id=policy_by_id,
            )
            final_return_code = attempt_result["return_code"] if isinstance(attempt_result["return_code"], int) else None
            current_game_day = game_day_key(datetime.now(local_tz), client=client)
            status_by_task_id = {
                task_id: status
                for task_id, status in attempt_result["status_by_task_id"].items()
                if status != "missing"
            }
            run_successful_task_ids.update(task_id for task_id, status in status_by_task_id.items() if status == "succeeded")
            self.store.update_daily_stats(
                schedule_id=config.id,
                game_day=current_game_day,
                task_names={task_id: policy_by_id[task_id].name for task_id in status_by_task_id if task_id in policy_by_id},
                task_statuses=status_by_task_id,
            )
            stats = self.store.daily_stats(config.id, current_game_day)
            next_task_ids = retry_task_ids(
                policies,
                entry,
                sorted_entries,
                stats,
                attempt_result["status_by_task_id"],
                run_successful_task_ids=run_successful_task_ids,
            )
            if next_task_ids and attempt_index < state.max_retries:
                self._append_framework_event(state, f"准备重试: {', '.join(_task_names(policy_by_id, next_task_ids))}", tone="warning")
                self._wait_retry_buffer(state, config, attempt_index)
            else:
                final_status = _final_status(policies, entry, sorted_entries, stats, attempt_result["status_by_task_id"], run_successful_task_ids)

        if state.stop_requested:
            final_status = "stopped"
        elif next_task_ids and final_status != "stopped":
            self._append_framework_event(state, "重试次数已达上限，仍有未成功子任务。", tone="danger")
            final_status = "failed"
        summary = {
            "final_status": final_status,
            "retries": attempt_index,
            "retry_groups": 1 if attempt_index else 0,
        }
        self._seal_current_retry_for_log(state, final_status, final_return_code, task_ids=next_task_ids)
        self.store.finish_run(
            state.id,
            status=final_status,
            retry_count=len(state.retries),
            retry_group_count=1 if attempt_index else 0,
            summary=summary,
            maacore_log_file=state.maacore_log_file,
        )
        self.store.enforce_retention()
        self.diagnostics.enforce_retention()
        logger.info(
            "scheduled run finished run_id=%s schedule_id=%s status=%s retries=%s return_code=%s",
            state.id,
            state.metadata.get("schedule_id"),
            final_status,
            attempt_index,
            final_return_code,
        )
        self._set_done(state, final_status, final_return_code)

    def _run_attempt(
        self,
        state: LiveRun,
        config: ScheduleConfig,
        *,
        task_ids: list[str],
        attempt_index: int,
        retry_group: int,
        policy_by_id: dict[str, TaskPolicy],
    ) -> dict[str, Any]:
        with self._lock:
            retry = state.current_retry
            if retry is None:
                retry = state.begin_retry(retry_group=retry_group, task_ids=task_ids, log=_new_schedule_log_buffer(include_script=bool(config.restart.script)), log_files=state.log_files)
            else:
                retry.retry_group = retry_group
                retry.task_ids = list(task_ids)
                retry.log_files = dict(state.log_files)
                retry.touch()
            self._notify_locked()
        prepare_messages: list[str] = []
        generated_profile = config.profile_name or f"{config.id}-profile"
        generated_run_id = f"schedule-{state.id}"
        run_task, run_env = prepare_maa_cli_task(
            self.runtime,
            config.task_config,
            run_id=generated_run_id,
            attempt=attempt_index,
            messages=prepare_messages,
            selected_task_ids=set(task_ids),
            force_enable_selected=True,
            profile_data=config.profile_data,
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
        log_level = int(state.metadata.get("log_level") or 0)
        if log_level > 0:
            cmd.extend(["-v"] * log_level)

        self._append_framework_event(state, f"开始第 {attempt_index} 次尝试: {', '.join(_task_names(policy_by_id, task_ids))}", tone="info")
        for message in prepare_messages:
            self._append_framework_event(state, message, tone="info")
        task_descriptors = _task_descriptors(policy_by_id, task_ids)
        retry.log.begin_task_sequence(_task_descriptor_dicts(task_descriptors))
        collector = MaaTaskResultCollector(task_descriptors)
        maacore_log_start = self.diagnostics.maacore_log_offset()
        result = run_streaming_process(
            self.runtime,
            cmd,
            env=run_env,
            on_output=lambda text: None,
            on_stream_output=lambda stream, text: self._append_maa_log(state, retry, text, stream),
            on_raw_line=lambda stream, line: collector.consume_raw_line(f"maa-cli:{stream}", line),
            on_process=lambda proc: self._set_process(state, proc),
            should_stop=lambda: state.stop_requested,
            should_force_stop=lambda: state.force_stop_requested,
            no_output_warning_seconds=config.timeouts.no_output_warning_seconds or None,
            no_output_kill_seconds=config.timeouts.no_output_kill_seconds or None,
            runtime_warning_seconds=config.timeouts.runtime_warning_seconds or None,
            runtime_kill_seconds=config.timeouts.runtime_kill_seconds or None,
            stop_warning_seconds=config.timeouts.stop_warning_seconds or None,
            stop_kill_seconds=config.timeouts.stop_kill_seconds or None,
            on_timeout=lambda level, elapsed: self._append_timeout_event(state, level, elapsed),
        )
        self._flush_maa_log(state, retry)
        collector.finish()
        task_results = list(collector.results)
        status_by_task_id = collector.status_by_task_id(task_ids)
        attempt_status = "succeeded" if result.return_code == 0 and all(status == "succeeded" for status in status_by_task_id.values()) else "failed"
        if result.stopped or state.stop_requested:
            attempt_status = "stopped"
        if result.timed_out:
            attempt_status = "failed"
        maacore_log_file = self.diagnostics.capture_maacore_log(retry.id, maacore_log_start)
        with self._lock:
            retry.task_results = task_results
            retry.maacore_log_file = maacore_log_file
            retry.generated_config_dir = relative_path(self.runtime.generated_config_dir / generated_run_id, self.runtime.repo_root)
            retry.seal(status=attempt_status, return_code=result.return_code)
            if maacore_log_file is not None:
                state.maacore_log_file = maacore_log_file
            state.process = None
            state.touch()
            self._notify_locked()

        self.store.add_retry(
            retry_id=retry.id,
            run_id=state.id,
            retry_index=attempt_index,
            retry_group=retry_group,
            status=attempt_status,
            started_at=retry.started_at,
            updated_at=retry.updated_at,
            ended_at=retry.ended_at or retry.updated_at,
            return_code=result.return_code,
            task_ids=task_ids,
            task_results=task_results,
            log_entries=retry.log.entries(),
            log_files=retry.log_files,
            generated_config_dir=retry.generated_config_dir,
            maacore_log_file=maacore_log_file,
        )
        return {
            "return_code": result.return_code,
            "status_by_task_id": status_by_task_id,
        }

    def _wait_retry_buffer(self, state: ScheduleRunState, config: ScheduleConfig, attempt_index: int) -> None:
        every = config.retry.buffer_every_retries
        seconds = config.retry.buffer_seconds
        if every <= 0 or seconds <= 0 or attempt_index % every != 0:
            return
        self._append_framework_event(state, f"已连续重试 {attempt_index} 次，缓冲等待 {seconds}s。", tone="warning")
        with self._condition:
            self._condition.wait_for(lambda: state.stop_requested, timeout=seconds)

    def _run_restart_script(self, state: ScheduleRunState, config: ScheduleConfig, mode: str) -> None:
        if config.restart.mode != mode or not config.restart.script:
            return
        try:
            command = self.scripts.command(config.restart.script, config.restart.variables)
        except FileNotFoundError:
            self._append_framework_event(state, f"重启脚本不存在: {config.restart.script}", tone="warning")
            return
        except Exception as exc:
            self._append_framework_event(state, f"重启脚本启动失败: {exc}", tone="danger")
            return

        self._append_framework_event(state, f"运行重启脚本({mode}): {config.restart.script}", tone="info")
        retry = self._ensure_retry_for_log(state)
        try:
            result = run_streaming_process(
                self.runtime,
                command.cmd,
                env=command.env,
                on_output=lambda text: None,
                on_stream_output=lambda stream, text: self._append_script_log(state, retry, text, stream),
                should_stop=lambda: state.stop_requested,
                runtime_kill_seconds=120,
                on_timeout=lambda level, elapsed: self._append_script_timeout_event(state, level, elapsed),
            )
            self._flush_run_log(state, retry)
        except Exception as exc:
            self._append_framework_event(state, f"重启脚本启动失败: {exc}", tone="danger")
            logger.exception("schedule restart script failed run_id=%s script=%s", state.id, config.restart.script)
            return
        if result.timed_out:
            self._append_framework_event(state, "重启脚本运行超时，已终止。", tone="danger")
        if result.return_code != 0:
            self._append_framework_event(state, f"重启脚本退出码: {result.return_code}", tone="warning")

    def _append_skip_events(
        self,
        state: ScheduleRunState,
        policy_by_id: dict[str, TaskPolicy],
        skipped: list[dict[str, str]],
        entry: ScheduleEntry,
    ) -> None:
        enabled = set(entry.task_ids)
        for item in skipped:
            task_id = item.get("task_id", "")
            if task_id not in enabled:
                continue
            task_name = policy_by_id[task_id].name if task_id in policy_by_id else task_id
            self._append_framework_event(state, f"跳过子任务: {task_name}，原因: {item.get('reason', '未说明')}", tone="info")

    def _mark_log_updated(self, state: ScheduleRunState) -> None:
        with self._lock:
            state.touch()
            self._notify_locked()

    def _append_framework_event(self, state: ScheduleRunState, text: str, *, tone: str = "info") -> None:
        self.diagnostics.append_run_event(state.id, "schedule", "framework", text, tone=tone)
        if tone == "danger":
            logger.error("scheduled run event run_id=%s text=%s", state.id, text)
        elif tone == "warning":
            logger.warning("scheduled run event run_id=%s text=%s", state.id, text)
        else:
            logger.info("scheduled run event run_id=%s text=%s", state.id, text)
        retry = self._ensure_retry_for_log(state)
        if retry.log.append(f"{text.rstrip()}\n", source="framework:event", metadata={"time": server_now_iso(), "tone": tone}):
            with self._lock:
                retry.touch()
                state.touch()
                self._notify_locked()

    def _append_maa_log(self, state: ScheduleRunState, retry: LiveRetry, text: str, stream: str = "output") -> None:
        self.diagnostics.append_maa_cli_output(state.id, stream, text)
        if retry.log.append(text, source=f"maa-cli:{stream}"):
            with self._lock:
                retry.touch()
                state.touch()
                self._notify_locked()

    def _flush_maa_log(self, state: ScheduleRunState, retry: LiveRetry) -> None:
        self._flush_run_log(state, retry)

    def _append_script_log(self, state: ScheduleRunState, retry: LiveRetry, text: str, stream: str = "output") -> None:
        self.diagnostics.append_script_output(state.id, stream, text)
        if retry.log.append(text, source=f"script:{stream}"):
            with self._lock:
                retry.touch()
                state.touch()
                self._notify_locked()

    def _flush_run_log(self, state: ScheduleRunState, retry: LiveRetry) -> None:
        if retry.log.flush():
            with self._lock:
                retry.touch()
                state.touch()
                self._notify_locked()

    def _append_timeout_event(self, state: ScheduleRunState, level: str, elapsed: float) -> None:
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
        self._append_framework_event(state, messages.get(level, f"运行超时事件: {level}"), tone=tone)

    def _append_script_timeout_event(self, state: ScheduleRunState, level: str, elapsed: float) -> None:
        if level == "runtime_kill":
            self._append_framework_event(state, f"重启脚本运行超过 {elapsed:.0f}s，正在终止。", tone="danger")

    def _set_process(self, state: ScheduleRunState, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            state.process = proc

    def _set_done(self, state: ScheduleRunState, status: str, return_code: int | None) -> None:
        with self._lock:
            state.finish(status=status, return_code=return_code)
            self._notify_locked()

    def _seal_current_retry_for_log(self, state: ScheduleRunState, status: str, return_code: int | None, *, task_ids: list[str] | None = None) -> None:
        with self._lock:
            retry = state.current_retry
            if retry is None:
                return
            if task_ids is not None:
                retry.task_ids = list(task_ids)
            retry.seal(status=status, return_code=return_code)
            state.touch()
            self._notify_locked()
        self.store.add_retry(
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
            generated_config_dir=retry.generated_config_dir,
            maacore_log_file=retry.maacore_log_file,
        )

    def _ensure_retry_for_log(self, state: ScheduleRunState) -> LiveRetry:
        with self._lock:
            retry = state.current_retry
            if retry is not None:
                return retry
            retry = state.begin_retry(log=_new_schedule_log_buffer(include_script=True), log_files=state.log_files)
            self._notify_locked()
        return retry

    def _notify_from_thread(self) -> None:
        with self._lock:
            self._notify_locked()

    def _notify_locked(self) -> None:
        self._version += 1
        self._condition.notify_all()


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
        for source in ("script:stdout", "script:stderr"):
            log.register_source(LogSourceSpec(source, default_tone_for_source(source), plain_translate_line))


def _new_schedule_log_buffer(*, include_script: bool) -> RunLogBuffer:
    log = RunLogBuffer(max_output_chunks=3000)
    _register_schedule_log_sources(log, include_script=include_script)
    return log


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


def _now() -> str:
    return server_now_iso()


def _retry_count(value: object) -> int:
    try:
        return min(50, max(1, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1
