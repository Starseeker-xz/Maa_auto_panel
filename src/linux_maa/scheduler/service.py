from __future__ import annotations

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from linux_maa.config import ConfigManager, FrameworkSettingsManager
from linux_maa.diagnostics import Diagnostics, get_logger
from linux_maa.logs import LogSourceSpec, RunLogBuffer, plain_translate_line
from linux_maa.logs.pipeline import default_tone_for_source
from linux_maa.maa.log_templates import register_maa_log_sources
from linux_maa.maa.runner import load_task_file, prepare_maa_cli_task, resolve_task_file
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.process import run_streaming_process
from linux_maa.run_state import RunStateStore
from linux_maa.scheduler.config import ScheduleConfigManager
from linux_maa.scheduler.models import DailyTaskStats, ScheduleConfig, ScheduleEntry, TaskPolicy
from linux_maa.scheduler.policy import initial_task_selection, remaining_enabled_slots, retry_task_ids, task_policies_from_config
from linux_maa.scheduler.scripts import ScheduleScriptManager
from linux_maa.scheduler.time import effective_timezone, extract_client_type, game_day_info, game_day_key, sort_entries_for_game_day
from linux_maa.state import idle_response
from linux_maa.utils import relative_path


logger = get_logger(__name__)


@dataclass
class ScheduleRunState:
    id: str
    schedule_id: str
    schedule_name: str
    entry_id: str
    entry_name: str
    task_config: str
    profile_name: str
    status: str
    created_at: str
    updated_at: str
    log_level: int
    game_day: str
    trigger: str
    return_code: int | None = None
    log_file: str | None = None
    log_files: dict[str, str] = field(default_factory=dict)
    maacore_log_file: str | None = None
    maacore_log_start: int = 0
    log: RunLogBuffer = field(default_factory=lambda: RunLogBuffer(max_output_chunks=3000))
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    stop_requested: bool = False
    thread: threading.Thread | None = field(default=None, repr=False)

    def to_dict(self, *, include_logs: bool = True) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "schedule_id": self.schedule_id,
            "schedule_name": self.schedule_name,
            "entry_id": self.entry_id,
            "entry_name": self.entry_name,
            "task_config": self.task_config,
            "profile": self.profile_name,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "log_level": self.log_level,
            "game_day": self.game_day,
            "trigger": self.trigger,
            "return_code": self.return_code,
            "log_file": self.log_file,
            "log_files": dict(self.log_files),
            "maacore_log_file": self.maacore_log_file,
        }
        if include_logs:
            data.update(self.log.to_dict())
        return data


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
                from linux_maa.config import ConfigValidationFailure

                raise ConfigValidationFailure(validation)
        config = self.schedules.write(schedule_id, payload)
        logger.info("schedule saved schedule_id=%s", schedule_id)
        return self._schedule_response(config)

    def delete_schedule(self, schedule_id: str) -> dict[str, object]:
        logger.warning("schedule deleted schedule_id=%s", schedule_id)
        return {"deleted": self.schedules.delete(schedule_id).to_dict()}

    def start_now(self, schedule_id: str, entry_id: str | None = None) -> ScheduleRunState:
        config = self.schedules.read(schedule_id)
        entry = next((item for item in config.entries if item.id == entry_id), None) if entry_id else None
        entry = entry or config.entries[0]
        return self._start_run(config, entry, trigger="manual")

    def current(self) -> ScheduleRunState | None:
        with self._lock:
            return self._current

    def current_response(self, schedule_id: str | None = None, *, include_logs: bool = True) -> dict[str, object]:
        with self._lock:
            current = self._current
            version = self._version
            if current is None or (schedule_id is not None and current.schedule_id != schedule_id):
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
            self._current.stop_requested = True
            if self._current.process and self._current.process.poll() is None:
                self.diagnostics.append_run_event(self._current.id, "schedule", "framework", "收到停止请求，正在终止 maa-cli...", tone="warning")
                self._append_framework_event(self._current, "收到停止请求，正在终止 maa-cli...", tone="warning")
                self._current.process.terminate()
            logger.warning("scheduled run stop requested run_id=%s schedule_id=%s", self._current.id, self._current.schedule_id)
            self._current.status = "stopping"
            self._current.updated_at = _now()
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

    def _start_run(self, config: ScheduleConfig, entry: ScheduleEntry, *, trigger: str) -> ScheduleRunState:
        with self._lock:
            if self._current and self._current.status in {"running", "stopping"}:
                raise RuntimeError(f"Scheduled run already active: {self._current.id}")

            task_data = load_task_file(resolve_task_file(self.runtime, config.task_config))
            client = extract_client_type(task_data)
            timezone_name = str(self.framework_settings.read()["effective_timezone"]["name"])
            game_day = game_day_key(datetime.now(effective_timezone(timezone_name)), client=client)
            now = _now()
            run_id = uuid.uuid4().hex[:12]
            state = ScheduleRunState(
                id=run_id,
                schedule_id=config.id,
                schedule_name=config.name,
                entry_id=entry.id,
                entry_name=entry.name,
                task_config=config.task_config,
                profile_name=config.profile_name,
                status="running",
                created_at=now,
                updated_at=now,
                log_level=config.log_level,
                game_day=game_day,
                trigger=trigger,
            )
            state.log_file = self.diagnostics.maa_cli_log_file(run_id)
            state.log_files = self.diagnostics.maa_cli_log_files(run_id)
            _register_schedule_log_sources(state.log, include_script=bool(config.restart.script))
            if config.restart.script:
                state.log_files.update(self.diagnostics.script_log_files(run_id))
            state.maacore_log_start = self.diagnostics.maacore_log_offset()
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
        stats = self.store.daily_stats(config.id, state.game_day)
        selection = initial_task_selection(policies, entry, stats)
        selected = selection.selected
        self.store.create_run(
            run_id=state.id,
            schedule_id=config.id,
            schedule_name=config.name,
            entry_id=entry.id,
            entry_name=entry.name,
            task_config=config.task_config,
            game_day=state.game_day,
            trigger=state.trigger,
            selected_task_ids=selected,
            log_file=state.log_file,
            log_files=state.log_files,
            event_log_file=self.diagnostics.event_log_file(state.id),
        )

        if not selected:
            self._append_framework_event(state, "本次没有需要运行的子任务。", tone="info")
            self._append_skip_events(state, policy_by_id, selection.skipped, entry)
            self.store.finish_run(
                state.id,
                status="skipped",
                attempt_count=0,
                retry_group_count=0,
                log_file=state.log_file,
                log_files=state.log_files,
                summary={"reason": "no-selected-tasks"},
            )
            self.store.enforce_retention()
            self.diagnostics.enforce_retention()
            self._set_done(state, "skipped", 0)
            return

        self._append_framework_event(state, f"本次运行实际任务: {', '.join(_task_names(policy_by_id, selected))}", tone="info")
        self._append_skip_events(state, policy_by_id, selection.skipped, entry)
        self._run_restart_script(state, config, "before_run")

        retry_group = 1
        attempt_index = 0
        attempt_in_group = 0
        next_task_ids = selected
        final_status = "failed"
        final_return_code: int | None = None
        final_log_file: str | None = None
        run_successful_task_ids: set[str] = set()

        while next_task_ids and not state.stop_requested:
            if attempt_in_group >= config.retry.max_attempts_per_group:
                if retry_group >= config.retry.max_groups:
                    self._append_framework_event(state, "重试组次数已达上限，放弃本次定时运行。", tone="danger")
                    break
                retry_group += 1
                attempt_in_group = 0
                self._append_framework_event(state, f"进入第 {retry_group} 个重试组，缓冲 {config.retry.group_buffer_seconds}s。", tone="warning")
                self._run_restart_script(state, config, "before_retry_group")
                if config.retry.group_buffer_seconds:
                    time.sleep(config.retry.group_buffer_seconds)

            attempt_index += 1
            attempt_in_group += 1
            if attempt_index > 1:
                self._run_restart_script(state, config, "before_retry")
            attempt_result = self._run_attempt(
                state,
                config,
                task_ids=next_task_ids,
                attempt_index=attempt_index,
                retry_group=retry_group,
                policy_by_id=policy_by_id,
            )
            final_return_code = attempt_result["return_code"] if isinstance(attempt_result["return_code"], int) else None
            final_log_file = attempt_result.get("log_file") if isinstance(attempt_result.get("log_file"), str) else final_log_file
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
            if next_task_ids:
                self._append_framework_event(state, f"准备重试: {', '.join(_task_names(policy_by_id, next_task_ids))}", tone="warning")
            else:
                final_status = _final_status(policies, entry, sorted_entries, stats, attempt_result["status_by_task_id"], run_successful_task_ids)

        if state.stop_requested:
            final_status = "stopped"
        summary = {
            "final_status": final_status,
            "attempts": attempt_index,
            "retry_groups": retry_group,
        }
        maacore_log_file = self.diagnostics.capture_maacore_log(state.id, state.maacore_log_start)
        if maacore_log_file is not None:
            state.maacore_log_file = maacore_log_file
        self.store.finish_run(
            state.id,
            status=final_status,
            attempt_count=attempt_index,
            retry_group_count=retry_group,
            log_file=final_log_file,
            log_files=state.log_files,
            summary=summary,
            maacore_log_file=maacore_log_file,
        )
        self.store.enforce_retention()
        self.diagnostics.enforce_retention()
        logger.info(
            "scheduled run finished run_id=%s schedule_id=%s status=%s attempts=%s return_code=%s",
            state.id,
            state.schedule_id,
            final_status,
            attempt_index,
            final_return_code,
        )
        self._set_done(state, final_status, final_return_code)

    def _run_attempt(
        self,
        state: ScheduleRunState,
        config: ScheduleConfig,
        *,
        task_ids: list[str],
        attempt_index: int,
        retry_group: int,
        policy_by_id: dict[str, TaskPolicy],
    ) -> dict[str, Any]:
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
        if state.log_level > 0:
            cmd.extend(["-v"] * state.log_level)

        self._append_framework_event(state, f"开始第 {attempt_index} 次尝试: {', '.join(_task_names(policy_by_id, task_ids))}", tone="info")
        state.log.begin_task_sequence(_expected_log_tasks(policy_by_id, task_ids))
        for message in prepare_messages:
            self._append_framework_event(state, message, tone="info")
        attempt_started = _now()
        translator_start = len(state.log.task_results())
        log_entry_start = len(state.log.entries())
        result = run_streaming_process(
            self.runtime,
            cmd,
            env=run_env,
            on_output=lambda text: None,
            on_stream_output=lambda stream, text: self._append_maa_log(state, text, stream),
            on_process=lambda proc: self._set_process(state, proc),
            should_stop=lambda: state.stop_requested,
            timeout_seconds=config.timeouts.run_kill_seconds or None,
            warning_seconds=config.timeouts.run_warning_seconds or None,
            danger_seconds=config.timeouts.run_danger_seconds or None,
            on_timeout=lambda level, elapsed: self._append_timeout_event(state, level, elapsed),
            on_tick=self._child_timeout_checker(state, config),
        )
        self._flush_maa_log(state)
        task_results = state.log.task_results()[translator_start:]
        log_entries = state.log.entries()[log_entry_start:]
        status_by_task_id = _status_by_task_id(task_ids, policy_by_id, task_results)
        attempt_status = "succeeded" if result.return_code == 0 and all(status == "succeeded" for status in status_by_task_id.values()) else "failed"
        if result.stopped or state.stop_requested:
            attempt_status = "stopped"
        if result.timed_out:
            attempt_status = "failed"

        self.store.add_attempt(
            attempt_id=f"{state.id}-{attempt_index}",
            run_id=state.id,
            attempt_index=attempt_index,
            retry_group=retry_group,
            status=attempt_status,
            started_at=attempt_started,
            ended_at=_now(),
            return_code=result.return_code,
            task_ids=task_ids,
            task_results=task_results,
            log_entries=log_entries,
            log_file=state.log_file,
            log_files=state.log_files,
            generated_config_dir=relative_path(self.runtime.generated_config_dir / generated_run_id, self.runtime.repo_root),
        )
        return {
            "return_code": result.return_code,
            "log_file": state.log_file,
            "status_by_task_id": status_by_task_id,
        }

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
        try:
            result = run_streaming_process(
                self.runtime,
                command.cmd,
                env=command.env,
                on_output=lambda text: None,
                on_stream_output=lambda stream, text: self._append_script_log(state, text, stream),
                should_stop=lambda: state.stop_requested,
                timeout_seconds=120,
                on_timeout=lambda level, elapsed: self._append_script_timeout_event(state, level, elapsed),
            )
            self._flush_run_log(state)
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
            state.updated_at = _now()
            self._notify_locked()

    def _append_framework_event(self, state: ScheduleRunState, text: str, *, tone: str = "info") -> None:
        self.diagnostics.append_run_event(state.id, "schedule", "framework", text, tone=tone)
        if tone == "danger":
            logger.error("scheduled run event run_id=%s text=%s", state.id, text)
        elif tone == "warning":
            logger.warning("scheduled run event run_id=%s text=%s", state.id, text)
        else:
            logger.info("scheduled run event run_id=%s text=%s", state.id, text)
        if state.log.append(f"{text.rstrip()}\n", source="framework:event", metadata={"time": datetime.now().strftime("%H:%M:%S"), "tone": tone}):
            self._mark_log_updated(state)

    def _append_maa_log(self, state: ScheduleRunState, text: str, stream: str = "output") -> None:
        self.diagnostics.append_maa_cli_output(state.id, stream, text)
        if state.log.append(text, source=f"maa-cli:{stream}"):
            self._mark_log_updated(state)

    def _flush_maa_log(self, state: ScheduleRunState) -> None:
        self._flush_run_log(state)

    def _append_script_log(self, state: ScheduleRunState, text: str, stream: str = "output") -> None:
        self.diagnostics.append_script_output(state.id, stream, text)
        if state.log.append(text, source=f"script:{stream}"):
            self._mark_log_updated(state)

    def _flush_run_log(self, state: ScheduleRunState) -> None:
        if state.log.flush():
            self._mark_log_updated(state)

    def _append_timeout_event(self, state: ScheduleRunState, level: str, elapsed: float) -> None:
        if level == "warning":
            self._append_framework_event(state, f"运行时间已超过 {elapsed:.0f}s。", tone="warning")
        elif level == "danger":
            self._append_framework_event(state, f"运行时间已超过 {elapsed:.0f}s，即将触发硬停止。", tone="danger")
        else:
            self._append_framework_event(state, f"运行时间已超过上限，正在终止 maa-cli。", tone="danger")

    def _append_script_timeout_event(self, state: ScheduleRunState, level: str, elapsed: float) -> None:
        if level == "kill":
            self._append_framework_event(state, f"重启脚本运行超过 {elapsed:.0f}s，正在终止。", tone="danger")

    def _child_timeout_checker(self, state: ScheduleRunState, config: ScheduleConfig):
        warned_task = ""
        dangered_task = ""
        killed_task = ""

        def check() -> None:
            nonlocal warned_task, dangered_task, killed_task
            current = state.log.current_block_elapsed_seconds(kind="task")
            if current is None:
                return
            task_name, elapsed = current
            if config.timeouts.child_warning_seconds and warned_task != task_name and elapsed >= config.timeouts.child_warning_seconds:
                warned_task = task_name
                self._append_framework_event(state, f"子任务 {task_name} 已运行 {elapsed:.0f}s。", tone="warning")
            if config.timeouts.child_danger_seconds and dangered_task != task_name and elapsed >= config.timeouts.child_danger_seconds:
                dangered_task = task_name
                self._append_framework_event(state, f"子任务 {task_name} 已运行 {elapsed:.0f}s，即将触发硬停止。", tone="danger")
            if config.timeouts.child_kill_seconds and killed_task != task_name and elapsed >= config.timeouts.child_kill_seconds:
                killed_task = task_name
                state.stop_requested = True
                self._append_framework_event(state, f"子任务 {task_name} 超过上限，正在终止 maa-cli。", tone="danger")

        return check

    def _set_process(self, state: ScheduleRunState, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            state.process = proc

    def _set_done(self, state: ScheduleRunState, status: str, return_code: int | None) -> None:
        with self._lock:
            state.status = status
            state.return_code = return_code
            state.updated_at = _now()
            state.process = None
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


def _status_by_task_id(task_ids: list[str], policy_by_id: dict[str, TaskPolicy], task_results: list[dict[str, Any]]) -> dict[str, str]:
    unused = list(task_results)
    output: dict[str, str] = {}
    for task_id in task_ids:
        policy = policy_by_id.get(task_id)
        if policy is None:
            output[task_id] = "missing"
            continue
        match_index = next(
            (
                index
                for index, result in enumerate(unused)
                if result.get("task_id") == task_id
                or result.get("source_name") == policy.type
                or result.get("name") == policy.type
            ),
            -1,
        )
        if match_index < 0:
            output[task_id] = "missing"
            continue
        matched = unused.pop(match_index)
        output[task_id] = str(matched.get("status") or "unknown")
    return output


def _task_names(policy_by_id: dict[str, TaskPolicy], task_ids: list[str]) -> list[str]:
    return [policy_by_id[task_id].name if task_id in policy_by_id else task_id for task_id in task_ids]


def _expected_log_tasks(policy_by_id: dict[str, TaskPolicy], task_ids: list[str]) -> list[dict[str, str]]:
    return [
        {"task_id": task_id, "source_name": policy_by_id[task_id].type, "name": policy_by_id[task_id].name}
        for task_id in task_ids
        if task_id in policy_by_id
    ]


def _register_schedule_log_sources(log: RunLogBuffer, *, include_script: bool) -> None:
    register_maa_log_sources(log)
    if include_script:
        for source in ("script:stdout", "script:stderr"):
            log.register_source(LogSourceSpec(source, default_tone_for_source(source), plain_translate_line))


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
    return datetime.now().isoformat(timespec="seconds")
