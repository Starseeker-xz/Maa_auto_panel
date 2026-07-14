from __future__ import annotations

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass

from maa_auto_panel.diagnostics import Diagnostics, get_logger
from maa_auto_panel.errors import Conflict, ResourceNotFound, RuntimeUnavailable
from maa_auto_panel.logs.records import LogMessage
from maa_auto_panel.process import (
    RawLineCallback,
    StreamingProcessResult,
    TimeoutCallback,
    force_kill_process_group,
    run_streaming_process,
    terminate_process_group,
)
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.contracts import (
    LogConfigurator,
    RetryDecision,
    RunCompletion,
    RunFinishedListener,
    RunScriptSpec,
    RunStartPlan,
)
from maa_auto_panel.run_manager.coordinator import (
    RunConflictError,
    RunCoordinator,
    RunLease,
    RunResourceCancelledError,
    RunResourceTimeoutError,
)
from maa_auto_panel.run_manager.logs import RunLogProfile
from maa_auto_panel.run_manager.state import LiveRetry, LiveRun, RunKind, RunTimeouts, now_text
from maa_auto_panel.run_manager.store import RunStateStore
from maa_auto_panel.state import idle_response
from maa_auto_panel.time_utils import server_now_iso


logger = get_logger(__name__)

TERMINAL_STATUSES = {"succeeded", "failed", "soft_failed", "stopped", "skipped"}
FINALIZATION_PERSIST_ATTEMPTS = 3


class RunCallbackAPI:
    """Small callback facade for events and stop-aware waits; lifecycle stays internal."""

    def __init__(self, manager: GenericRunManager, state: LiveRun, plan: RunStartPlan, retry: LiveRetry | None = None) -> None:
        self._manager = manager
        self._state = state
        self._plan = plan
        self._retry = retry

    @property
    def run_id(self) -> str:
        return self._state.id

    @property
    def kind(self) -> RunKind:
        return self._state.kind

    @property
    def title(self) -> str:
        return self._state.title

    @property
    def metadata(self) -> dict[str, object]:
        return dict(self._state.metadata)

    @property
    def stop_requested(self) -> bool:
        return self._state.stop_requested

    @property
    def force_stop_requested(self) -> bool:
        return self._state.force_stop_requested

    def add_event(self, text: str, *, tone: str = "info") -> None:
        self._manager.append_event(self._state, self._plan, text, tone=tone)

    def wait_for_stop(self, timeout: float | None = None) -> bool:
        return self._manager.wait_for_stop(self._state, timeout)

    def configure_log(self, callback: LogConfigurator) -> None:
        if self._retry is None:
            return
        callback(self._retry.log)
        self._manager.mark_updated(self._state, self._retry)

    def mark_updated(self) -> None:
        self._manager.mark_updated(self._state, self._retry)


@dataclass(frozen=True)
class RunAttempt:
    """Read-only attempt view passed to callbacks."""

    api: RunCallbackAPI
    run_id: str
    retry_id: str
    retry_index: int
    attempt_index: int
    max_retries: int
    payload: dict[str, object]
    previous_decision: RetryDecision | None = None

    @property
    def stop_requested(self) -> bool:
        return self.api.stop_requested

    @property
    def force_stop_requested(self) -> bool:
        return self.api.force_stop_requested

    @property
    def metadata(self) -> dict[str, object]:
        return self.api.metadata

    def add_event(self, text: str, *, tone: str = "info") -> None:
        self.api.add_event(text, tone=tone)

    def wait_for_stop(self, timeout: float | None = None) -> bool:
        return self.api.wait_for_stop(timeout)

    def configure_log(self, callback: LogConfigurator) -> None:
        self.api.configure_log(callback)

    def mark_updated(self) -> None:
        self.api.mark_updated()


class GenericRunManager:
    """Generic live-run state machine and lifecycle owner."""

    def __init__(
        self,
        store: RunStateStore,
        diagnostics: Diagnostics,
        coordinator: RunCoordinator | None = None,
        on_run_finished: RunFinishedListener | None = None,
        resource_wait_timeout_seconds: Callable[[], float] | None = None,
    ) -> None:
        self.store = store
        self.diagnostics = diagnostics
        self.coordinator = coordinator or RunCoordinator()
        self.on_run_finished = on_run_finished
        self.resource_wait_timeout_seconds = resource_wait_timeout_seconds or (lambda: 300.0)
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._version = 0
        self._runs: dict[str, LiveRun] = {}
        self._plans: dict[str, RunStartPlan] = {}
        self._current_run_id: str | None = None
        self._closing = False

    def start(self, plan: RunStartPlan, *, run_id: str | None = None) -> LiveRun:
        with self._lock:
            if self._closing:
                raise RuntimeUnavailable("Application is shutting down")
        run_id = run_id or uuid.uuid4().hex[:12]
        started_at = now_text()
        state = LiveRun(
            id=run_id,
            kind=plan.kind,
            title=plan.title,
            status="running",
            started_at=started_at,
            updated_at=started_at,
            max_retries=_retry_count(plan.max_retries),
            log_files=dict(plan.log_files),
            event_log_file=plan.event_log_file,
            metadata=dict(plan.metadata),
            artifacts=dict(plan.artifacts),
        )
        lease = RunLease(
            run_id=run_id,
            kind=plan.kind,
            title=plan.title,
            priority=plan.priority_value(),
            resources=plan.resources,
            request_stop=lambda: self._request_stop_for_run(state),
            request_force_stop=lambda: self._request_force_stop_for_run(state),
            force_after_seconds=plan.force_after_seconds,
            preemptible=plan.preemptible,
        )
        thread = threading.Thread(target=self._execute_loop, args=(state, plan, lease), name=f"run-{state.id}", daemon=False)
        state.thread = thread
        start_error: Exception | None = None
        with self._lock:
            if self._closing:
                raise RuntimeUnavailable("Application is shutting down")
            self._discard_terminal_runs_locked()
            current = self._runs.get(self._current_run_id or "")
            if current and current.status in {"running", "stopping"}:
                raise Conflict(f"Run already active: {current.id}")
            self.store.create_run(
                run_id=run_id,
                kind=plan.kind,
                title=plan.title,
                max_retries=state.max_retries,
                log_files=state.log_files,
                event_log_file=state.event_log_file,
                metadata=plan.metadata,
                artifacts=plan.artifacts,
                history_scope=plan.history_scope,
            )
            self._runs[run_id] = state
            self._plans[run_id] = plan
            self._current_run_id = run_id
            try:
                thread.start()
            except Exception as exc:
                start_error = exc
            self._notify_locked()

        if start_error is not None:
            self.append_event(state, plan, plan.text.execution_failed.format(error=start_error), tone="danger")
            retry = state.current_retry
            if retry is not None:
                self._finish_retry(state, retry, "failed", None)
            self._finish_run(state, RunCompletion(status="failed"))
            raise start_error
        return state

    def current(self) -> LiveRun | None:
        with self._lock:
            return self._runs.get(self._current_run_id or "")

    def get(self, run_id: str) -> LiveRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def discard_terminal(self, run_id: str) -> None:
        """Forget a deleted terminal snapshot without affecting active work."""
        with self._lock:
            state = self._runs.get(run_id)
            if state is None:
                return
            if state.status not in TERMINAL_STATUSES:
                raise Conflict(f"Run is still active: {run_id}")
            self._runs.pop(run_id, None)
            self._plans.pop(run_id, None)
            if self._current_run_id == run_id:
                self._current_run_id = None
            self._notify_locked()

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

    def begin_shutdown(self) -> None:
        with self._condition:
            self._closing = True
            self._notify_locked()

    def request_shutdown_stop(self) -> LiveRun | None:
        state = self.current()
        if state is None or state.status not in {"running", "stopping"}:
            return None
        return self.stop(state.id)

    def request_shutdown_force(self) -> LiveRun | None:
        state = self.current()
        if state is None or state.status not in {"running", "stopping"}:
            return None
        return self.force_stop(state.id)

    def join_until(self, deadline: float) -> bool:
        state = self.current()
        thread = state.thread if state is not None else None
        if thread is None:
            return True
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
        return not thread.is_alive()

    def stop_current(self) -> LiveRun:
        state = self.current()
        if state is None:
            raise ResourceNotFound("No run active")
        return self.stop(state.id)

    def force_stop_current(self) -> LiveRun:
        state = self.current()
        if state is None:
            raise ResourceNotFound("No run active")
        return self.force_stop(state.id)

    def stop(self, run_id: str) -> LiveRun:
        state = self.get(run_id)
        if state is None:
            raise ResourceNotFound(f"Run not found: {run_id}")
        plan = self._plan_for(state)
        record_event = False
        with self._lock:
            if state.status in {"running", "stopping"}:
                if not state.stop_requested:
                    record_event = True
                    self._append_event_locked(state, plan, plan.text.stop_requested, tone="warning")
                state.request_stop()
                process = state.process
                self._notify_locked()
            else:
                process = None
        if record_event:
            self._record_framework_event(state, plan.text.stop_requested, tone="warning")
        self.coordinator.notify_waiters()
        terminate_process_group(process)
        return state

    def force_stop(self, run_id: str) -> LiveRun:
        state = self.get(run_id)
        if state is None:
            raise ResourceNotFound(f"Run not found: {run_id}")
        plan = self._plan_for(state)
        record_event = False
        with self._lock:
            if state.status in {"running", "stopping"}:
                if not state.force_stop_requested:
                    record_event = True
                    self._append_event_locked(state, plan, plan.text.force_stop_requested, tone="danger")
                state.request_force_stop()
                process = state.process
                self._notify_locked()
            else:
                process = None
        if record_event:
            self._record_framework_event(state, plan.text.force_stop_requested, tone="danger")
        self.coordinator.notify_waiters()
        force_kill_process_group(process)
        return state

    def append_event(self, state: LiveRun, plan: RunStartPlan, text: str, *, tone: str = "info") -> None:
        if not text:
            return
        self._record_framework_event(state, text, tone=tone)
        with self._lock:
            self._append_event_locked(state, plan, text, tone=tone)
            self._notify_locked()

    def append_log(
        self,
        state: LiveRun,
        retry: LiveRetry,
        text: str,
        *,
        source: str = "output",
        metadata: dict[str, object] | None = None,
    ) -> None:
        if retry.log.append(text, source=source, metadata=metadata):
            self.mark_updated(state, retry)

    def flush_log(self, state: LiveRun, retry: LiveRetry) -> None:
        if retry.log.flush():
            self.mark_updated(state, retry)

    def run_process(
        self,
        state: LiveRun,
        retry: LiveRetry,
        command: CommandSpec,
        *,
        log_profile: RunLogProfile,
        timeouts: RunTimeouts,
        on_raw_line: RawLineCallback | None = None,
        on_timeout: TimeoutCallback | None = None,
    ) -> StreamingProcessResult:
        try:
            return run_streaming_process(
                command.cmd,
                cwd=command.cwd,
                env=command.env,
                on_output=lambda text: None,
                on_stream_output=lambda stream, text: self._append_stream_output(state, retry, log_profile, stream, text),
                on_raw_line=on_raw_line,
                output_log_file=command.output_log_file,
                on_process=lambda proc: self.set_process(state, proc),
                should_stop=lambda: state.stop_requested,
                should_force_stop=lambda: state.force_stop_requested,
                no_output_warning_seconds=timeouts.no_output_warning_seconds or None,
                no_output_kill_seconds=timeouts.no_output_kill_seconds or None,
                runtime_warning_seconds=timeouts.runtime_warning_seconds or None,
                runtime_kill_seconds=timeouts.runtime_kill_seconds or None,
                stop_warning_seconds=timeouts.stop_warning_seconds or None,
                stop_kill_seconds=timeouts.stop_kill_seconds or None,
                on_timeout=on_timeout,
            )
        finally:
            self.flush_log(state, retry)
            self.set_process(state, None)

    def mark_updated(self, state: LiveRun, retry: LiveRetry | None = None) -> None:
        with self._lock:
            if retry is not None:
                retry.touch()
            state.touch()
            self._notify_locked()

    def set_process(self, state: LiveRun, proc: subprocess.Popen[str] | None) -> None:
        with self._lock:
            state.process = proc

    def wait_for_stop(self, state: LiveRun, timeout: float | None = None) -> bool:
        with self._condition:
            return self._condition.wait_for(lambda: state.stop_requested, timeout=timeout)

    def _execute_loop(self, state: LiveRun, plan: RunStartPlan, lease: RunLease) -> None:
        final_completion = RunCompletion(status="failed")
        previous_decision: RetryDecision | None = None
        next_command = plan.command
        next_payload = dict(plan.initial_attempt_payload)

        try:
            for attempt_index in range(1, state.max_retries + 1):
                if state.stop_requested:
                    final_completion = RunCompletion(status="stopped", return_code=final_completion.return_code)
                    break

                retry = self._begin_retry(state, plan)
                attempt = RunAttempt(
                    api=RunCallbackAPI(self, state, plan, retry),
                    run_id=state.id,
                    retry_id=retry.id,
                    retry_index=retry.retry_index,
                    attempt_index=attempt_index,
                    max_retries=state.max_retries,
                    payload=dict(next_payload),
                    previous_decision=previous_decision,
                )

                start_decision = self._run_start_hooks_if_needed(attempt, plan, attempt_index)
                if start_decision is not None:
                    final_completion = self._completion_from_decision(start_decision, fallback_status=start_decision.retry_status)
                    final_completion = self._run_finish_callback(attempt.api, plan, final_completion)
                    self._run_scripts(state, plan, retry, attempt, "after_run")
                    self._finish_retry_from_decision(state, retry, start_decision)
                    break

                if attempt_index == 1:
                    try:
                        self.coordinator.acquire(
                            lease,
                            timeout_seconds=max(0.0, self.resource_wait_timeout_seconds()),
                            on_wait=lambda blockers: self._report_resource_wait(attempt, blockers),
                            should_cancel=lambda: state.stop_requested,
                        )
                    except RunResourceCancelledError:
                        decision = RetryDecision("stopped", None, continue_retry=False, run_status="stopped")
                        self._finish_retry_from_decision(state, retry, decision)
                        final_completion = RunCompletion(status="stopped")
                        break
                    except RunConflictError as exc:
                        attempt.add_event(self._resource_conflict_message(exc), tone="danger")
                        decision = RetryDecision("failed", None, continue_retry=False, run_status="failed")
                        final_completion = self._completion_from_decision(decision, fallback_status="failed")
                        final_completion = self._run_finish_callback(attempt.api, plan, final_completion)
                        self._run_scripts(state, plan, retry, attempt, "after_run")
                        self._finish_retry_from_decision(state, retry, decision)
                        break
                    self._report_resource_acquired(attempt)
                    if state.stop_requested:
                        decision = RetryDecision("stopped", None, continue_retry=False, run_status="stopped")
                        self._finish_retry_from_decision(state, retry, decision)
                        final_completion = RunCompletion(status="stopped")
                        break

                command = self._command_for(plan, attempt, next_command)
                if command is None:
                    decision = RetryDecision("failed", None, continue_retry=False)
                    attempt.add_event(plan.text.start_failed.format(error="no command"), tone="danger")
                else:
                    decision = self._run_attempt_command(state, plan, retry, attempt, command)

                decision = self._after_attempt(state, plan, retry, attempt, decision)
                if state.stop_requested:
                    decision.continue_retry = False
                    if decision.retry_status == "failed":
                        decision.retry_status = "stopped"
                    if decision.run_status is None:
                        decision.run_status = "stopped"
                should_continue = bool(decision.continue_retry and attempt_index < state.max_retries and not state.stop_requested)
                if should_continue and plan.text.retry_next:
                    attempt.add_event(plan.text.retry_next, tone="warning")
                elif decision.continue_retry and attempt_index >= state.max_retries and plan.text.retry_limit_reached:
                    attempt.add_event(plan.text.retry_limit_reached, tone="danger")

                if should_continue:
                    next_command = decision.next_command or next_command
                    next_payload = dict(decision.next_attempt_payload or next_payload)
                else:
                    final_completion = self._completion_from_decision(decision, fallback_status=decision.retry_status)
                    final_completion = self._run_finish_callback(attempt.api, plan, final_completion)
                    self._run_scripts(state, plan, retry, attempt, "after_run")

                self._finish_retry_from_decision(state, retry, decision)
                if not should_continue:
                    break
                previous_decision = decision
            else:
                if state.stop_requested:
                    final_completion.status = "stopped"

            if state.stop_requested and final_completion.status == "failed":
                final_completion.status = "stopped"
            self._finish_run(state, final_completion)
        except Exception as exc:
            logger.exception("generic run loop failed run_id=%s kind=%s", state.id, state.kind)
            self.append_event(state, plan, plan.text.execution_failed.format(error=exc), tone="danger")
            retry = state.current_retry
            if retry is not None:
                self._finish_retry(
                    state,
                    retry,
                    "failed",
                    None,
                    metadata=retry.metadata,
                    artifacts=retry.artifacts,
                )
            try:
                self._finish_run(state, RunCompletion(status="failed"))
            except Exception:
                # Persistent storage failure is fail-closed: live and durable
                # remain non-terminal, the lease stays held, and startup recovery
                # will seal the durable record after the backend is restarted.
                logger.critical(
                    "run finalization could not be persisted; restart required run_id=%s kind=%s",
                    state.id,
                    state.kind,
                    exc_info=True,
                )

    def _report_resource_wait(self, attempt: RunAttempt, blockers: list[RunLease]) -> None:
        blocker_text = ", ".join(f"{item.title}({item.run_id})" for item in blockers)
        state = self._state_for(attempt)
        resource_wait = {
            "status": "waiting",
            "updated_at": now_text(),
            "blockers": [item.to_dict() for item in blockers],
        }
        with self._lock:
            state.metadata = {**state.metadata, "resource_wait": resource_wait}
            state.touch()
            self._notify_locked()
        self.store.update_run_metadata(state.id, {"resource_wait": resource_wait})
        attempt.add_event(f"等待运行资源释放: {blocker_text}", tone="warning")

    def _report_resource_acquired(self, attempt: RunAttempt) -> None:
        state = self._state_for(attempt)
        previous = state.metadata.get("resource_wait")
        if not isinstance(previous, dict) or previous.get("status") != "waiting":
            return
        resource_wait = {**previous, "status": "acquired", "updated_at": now_text(), "blockers": []}
        with self._lock:
            state.metadata = {**state.metadata, "resource_wait": resource_wait}
            state.touch()
            self._notify_locked()
        self.store.update_run_metadata(state.id, {"resource_wait": resource_wait})
        attempt.add_event("运行资源已取得，继续执行。", tone="info")

    def _resource_conflict_message(self, exc: RunConflictError) -> str:
        blocker_text = ", ".join(f"{item.title}({item.run_id})" for item in exc.blockers)
        if isinstance(exc, RunResourceTimeoutError):
            return f"等待运行资源超过全局上限 {exc.timeout_seconds:g} 秒，当前运行不会执行: {blocker_text}"
        return f"运行资源申请失败，当前运行不会执行: {blocker_text}"

    def _run_start_hooks_if_needed(self, attempt: RunAttempt, plan: RunStartPlan, attempt_index: int) -> RetryDecision | None:
        state = self._state_for(attempt)
        retry = self._retry_for(attempt)
        if attempt_index == 1:
            decision = plan.callbacks.on_start(attempt) if plan.callbacks.on_start is not None else None
            if decision is not None:
                return decision
            if state.stop_requested:
                return RetryDecision("stopped", None, run_status="stopped")
            self._run_scripts(state, plan, retry, attempt, "before_run")
            if state.stop_requested:
                return RetryDecision("stopped", None, run_status="stopped")
            if plan.text.start:
                attempt.add_event(plan.text.start.format(title=plan.title, retry_index=attempt.retry_index), tone="info")
            return None

        if state.stop_requested:
            return RetryDecision("stopped", None, run_status="stopped")
        if plan.callbacks.before_retry is not None and attempt.previous_decision is not None:
            plan.callbacks.before_retry(attempt, attempt.previous_decision)
        if state.stop_requested:
            return RetryDecision("stopped", None, run_status="stopped")
        self._run_scripts(state, plan, retry, attempt, "before_retry")
        if state.stop_requested:
            return RetryDecision("stopped", None, run_status="stopped")
        if plan.text.retry_start:
            attempt.add_event(plan.text.retry_start.format(title=plan.title, retry_index=attempt.retry_index), tone="warning")
        return None

    def _command_for(self, plan: RunStartPlan, attempt: RunAttempt, previous_command: CommandSpec | None) -> CommandSpec | None:
        if plan.callbacks.before_attempt is not None:
            plan.callbacks.before_attempt(attempt)
        if plan.callbacks.build_command is not None:
            return plan.callbacks.build_command(attempt)
        return previous_command

    def _run_attempt_command(
        self,
        state: LiveRun,
        plan: RunStartPlan,
        retry: LiveRetry,
        attempt: RunAttempt,
        command: CommandSpec,
    ) -> RetryDecision:
        try:
            result = self.run_process(
                state,
                retry,
                command,
                log_profile=plan.log_profile,
                timeouts=plan.timeouts,
                on_raw_line=lambda stream, line: self._handle_raw_line(plan, attempt, stream, line),
                on_timeout=lambda level, elapsed: self._append_timeout_event(attempt, level, elapsed),
            )
        except Exception as exc:
            attempt.add_event(plan.text.start_failed.format(error=exc), tone="danger")
            return RetryDecision("failed", None)

        decision = plan.callbacks.evaluate_attempt(attempt, result) if plan.callbacks.evaluate_attempt is not None else None
        if decision is None:
            decision = self._default_decision(state, result)
        if decision.return_code is None:
            decision.return_code = result.return_code
        if result.stopped or state.stop_requested:
            decision.continue_retry = False
            decision.retry_status = "stopped"
            decision.run_status = "stopped"
        self._append_default_result_event(attempt, plan, decision)
        return decision

    def _after_attempt(
        self,
        state: LiveRun,
        plan: RunStartPlan,
        retry: LiveRetry,
        attempt: RunAttempt,
        decision: RetryDecision,
    ) -> RetryDecision:
        if plan.callbacks.after_attempt is not None:
            updated = plan.callbacks.after_attempt(attempt, _result_from_decision(decision), decision)
            if updated is not None:
                decision = updated
        self._run_scripts(state, plan, retry, attempt, "after_retry")
        return decision

    def _run_finish_callback(self, api: RunCallbackAPI, plan: RunStartPlan, completion: RunCompletion) -> RunCompletion:
        if plan.callbacks.on_finish is None:
            return completion
        updated = plan.callbacks.on_finish(api, completion)
        return updated or completion

    def _run_scripts(
        self,
        state: LiveRun,
        plan: RunStartPlan,
        retry: LiveRetry,
        attempt: RunAttempt,
        hook: str,
    ) -> None:
        scripts = getattr(plan.script_hooks, hook)
        for script in scripts:
            try:
                command = script.command(attempt) if callable(script.command) else script.command
            except FileNotFoundError:
                attempt.add_event(f"脚本不存在: {script.label}", tone="warning")
                continue
            except Exception as exc:
                attempt.add_event(f"脚本启动失败: {exc}", tone="danger")
                continue
            if command is None:
                continue
            attempt.add_event(f"运行脚本({hook}): {script.label}", tone="info")
            profile = _script_profile(plan, script, hook)
            try:
                result = self.run_process(
                    state,
                    retry,
                    command,
                    log_profile=profile,
                    timeouts=script.timeouts,
                    on_timeout=lambda level, elapsed: self._append_script_timeout_event(attempt, level, elapsed),
                )
            except Exception as exc:
                attempt.add_event(f"脚本启动失败: {exc}", tone="danger")
                logger.exception("run script failed run_id=%s hook=%s label=%s", state.id, hook, script.label)
                continue
            if result.timed_out:
                attempt.add_event("脚本运行超时，已终止。", tone="danger")
            if result.return_code != 0:
                attempt.add_event(f"脚本退出码: {result.return_code}", tone="warning")

    def _begin_retry(self, state: LiveRun, plan: RunStartPlan) -> LiveRetry:
        with self._lock:
            retry = state.begin_retry(
                retry_group=1,
                log_files=state.log_files,
                log=plan.log_profile.new_buffer(),
            )
            self._notify_locked()
            return retry

    def _finish_retry_from_decision(self, state: LiveRun, retry: LiveRetry, decision: RetryDecision) -> None:
        self._finish_retry(
            state,
            retry,
            decision.retry_status,
            decision.return_code,
            metadata=decision.retry_metadata,
            artifacts=decision.retry_artifacts,
            summary_messages=decision.retry_summary_messages,
        )

    def _finish_retry(
        self,
        state: LiveRun,
        retry: LiveRetry,
        status: str,
        return_code: int | None,
        *,
        metadata: dict[str, object] | None = None,
        artifacts: dict[str, object] | None = None,
        summary_messages: list[LogMessage] | None = None,
    ) -> None:
        with self._lock:
            if retry.closed:
                return
            if metadata is not None:
                retry.metadata = dict(metadata)
            if artifacts is not None:
                retry.artifacts = dict(artifacts)
            if summary_messages is not None:
                retry.summary_messages = list(summary_messages)
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
            metadata=retry.metadata,
            artifacts=retry.artifacts,
            summary_messages=[message.to_dict() for message in retry.summary_messages],
            log_entries=retry.log.entries(),
            log_files=retry.log_files,
        )

    def _finish_run(self, state: LiveRun, completion: RunCompletion) -> None:
        with self._lock:
            if state.status in TERMINAL_STATUSES:
                return

        # Durable state is the recovery authority. Do not publish an irreversible
        # live terminal status until its durable counterpart has been committed.
        self._persist_completion(state, completion)

        with self._lock:
            if state.status in TERMINAL_STATUSES:
                return
            if completion.summary:
                state.metadata = {**state.metadata, "summary": dict(completion.summary)}
            if completion.metadata_patch:
                state.metadata = {**state.metadata, **completion.metadata_patch}
            if completion.artifacts:
                state.artifacts = {**state.artifacts, **completion.artifacts}
            state.finish(status=completion.status, return_code=completion.return_code)
            self._plans.pop(state.id, None)
            self._notify_locked()

        self.coordinator.release(state.id)
        logger.info("generic run finished run_id=%s kind=%s status=%s return_code=%s", state.id, state.kind, completion.status, completion.return_code)
        self._run_post_finish_maintenance(state)

    def _persist_completion(self, state: LiveRun, completion: RunCompletion) -> None:
        for attempt in range(1, FINALIZATION_PERSIST_ATTEMPTS + 1):
            try:
                self.store.finish_run(
                    state.id,
                    status=completion.status,
                    return_code=completion.return_code,
                    retry_count=len(state.retries),
                    retry_group_count=max((retry.retry_group for retry in state.retries), default=0),
                    metadata={**completion.metadata_patch, **({"summary": completion.summary} if completion.summary else {})},
                    artifacts=completion.artifacts,
                )
                return
            except Exception:
                if attempt >= FINALIZATION_PERSIST_ATTEMPTS:
                    raise
                logger.exception(
                    "run finalization persistence failed; retrying run_id=%s kind=%s attempt=%s/%s",
                    state.id,
                    state.kind,
                    attempt,
                    FINALIZATION_PERSIST_ATTEMPTS,
                )

    def _run_post_finish_maintenance(self, state: LiveRun) -> None:
        try:
            self.store.enforce_retention()
            self.diagnostics.enforce_retention(protected_paths=self.store.owned_paths())
        except Exception:
            logger.exception("run post-finish retention failed run_id=%s kind=%s", state.id, state.kind)
        if self.on_run_finished is not None:
            try:
                self.on_run_finished(state)
            except Exception:
                logger.exception("run finished listener failed run_id=%s kind=%s", state.id, state.kind)

    def _completion_from_decision(self, decision: RetryDecision, *, fallback_status: str) -> RunCompletion:
        return RunCompletion(
            status=decision.run_status or fallback_status,
            return_code=decision.return_code,
            summary=dict(decision.summary_patch),
            artifacts=dict(decision.retry_artifacts),
        )

    def _handle_raw_line(self, plan: RunStartPlan, attempt: RunAttempt, stream: str, line: str) -> None:
        if plan.callbacks.on_raw_line is not None:
            plan.callbacks.on_raw_line(attempt, stream, line)

    def _default_decision(self, state: LiveRun, result: StreamingProcessResult) -> RetryDecision:
        if result.stopped or state.stop_requested:
            return RetryDecision("stopped", result.return_code, run_status="stopped")
        if result.return_code == 0 and not result.timed_out:
            return RetryDecision("succeeded", result.return_code, run_status="succeeded")
        return RetryDecision("failed", result.return_code, continue_retry=True)

    def _append_default_result_event(self, attempt: RunAttempt, plan: RunStartPlan, decision: RetryDecision) -> None:
        if decision.retry_status == "succeeded" and plan.text.completed:
            attempt.add_event(plan.text.completed, tone="success")
            return
        if plan.text.exit_code:
            tone = "warning" if decision.retry_status == "stopped" else "danger"
            if decision.return_code == 0:
                tone = "info"
            attempt.add_event(plan.text.exit_code.format(return_code=decision.return_code), tone=tone)

    def _append_event_locked(self, state: LiveRun, plan: RunStartPlan, text: str, *, tone: str) -> None:
        retry = state.current_retry
        if retry is None:
            retry = state.begin_retry(log=plan.log_profile.new_buffer(), log_files=state.log_files)
        if retry.log.append(_ensure_newline(text), source="framework:event", metadata={"time": server_now_iso(), "tone": tone}):
            retry.touch()
        state.touch()

    def _append_stream_output(self, state: LiveRun, retry: LiveRetry, log_profile: RunLogProfile, stream: str, text: str) -> None:
        log_profile.append_diagnostics(state.id, stream, text)
        self.append_log(state, retry, text, source=log_profile.visible_source(stream))

    def _append_timeout_event(self, attempt: RunAttempt, level: str, elapsed: float) -> None:
        message = _timeout_message(level, elapsed, process_name=self._plan_for(self._state_for(attempt)).text.process_name)
        tone = "warning" if level.endswith("warning") else "danger"
        attempt.add_event(message, tone=tone)

    def _append_script_timeout_event(self, attempt: RunAttempt, level: str, elapsed: float) -> None:
        if level == "runtime_kill":
            attempt.add_event(f"脚本运行超过 {elapsed:.0f}s，正在终止。", tone="danger")

    def _record_framework_event(self, state: LiveRun, text: str, *, tone: str) -> None:
        self.diagnostics.append_run_event(state.id, state.kind, "framework", _ensure_newline(text), tone=tone)
        _log_framework_event(state, text, tone)

    def _request_stop_for_run(self, state: LiveRun) -> None:
        if self.get(state.id) is None:
            state.request_stop()
            return
        self.stop(state.id)

    def _request_force_stop_for_run(self, state: LiveRun) -> None:
        if self.get(state.id) is None:
            state.request_force_stop()
            return
        self.force_stop(state.id)

    def _plan_for(self, state: LiveRun) -> RunStartPlan:
        with self._lock:
            return self._plans[state.id]

    def _state_for(self, attempt: RunAttempt) -> LiveRun:
        state = self.get(attempt.run_id)
        if state is None:
            raise KeyError(attempt.run_id)
        return state

    def _retry_for(self, attempt: RunAttempt) -> LiveRetry:
        state = self._state_for(attempt)
        for retry in state.retries:
            if retry.id == attempt.retry_id:
                return retry
        raise KeyError(attempt.retry_id)

    def _notify_locked(self) -> None:
        self._version += 1
        self._condition.notify_all()

    def _discard_terminal_runs_locked(self) -> None:
        """Keep only active state plus the latest terminal snapshot until next run."""
        terminal_ids = [run_id for run_id, run in self._runs.items() if run.status in TERMINAL_STATUSES]
        for run_id in terminal_ids:
            self._runs.pop(run_id, None)
            self._plans.pop(run_id, None)
        if self._current_run_id in terminal_ids:
            self._current_run_id = None


def _script_profile(plan: RunStartPlan, script: RunScriptSpec, hook: str) -> RunLogProfile:
    base = script.log_profile or plan.script_log_profile
    return RunLogProfile(
        source_specs=base.source_specs,
        configure_buffer=base.configure_buffer,
        source_for_stream=lambda stream: f"{script.source_prefix}:{hook}:{stream}",
        diagnostic_sink=base.diagnostic_sink,
    )


def _result_from_decision(decision: RetryDecision) -> StreamingProcessResult:
    return StreamingProcessResult(return_code=decision.return_code or 0, timed_out=False, stopped=decision.retry_status == "stopped")


def _retry_count(value: object) -> int:
    try:
        return min(50, max(1, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1


def _ensure_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"


def _timeout_message(level: str, elapsed: float, *, process_name: str) -> str:
    messages = {
        "no_output_warning": f"已 {elapsed:.0f}s 没有收到新输出，运行可能卡住。",
        "no_output_kill": f"已 {elapsed:.0f}s 没有收到新输出，正在强制终止{process_name}。",
        "runtime_warning": f"运行时间已超过 {elapsed:.0f}s。",
        "runtime_kill": f"运行时间已超过上限，正在强制终止{process_name}。",
        "stop_warning": f"停止请求已等待 {elapsed:.0f}s，{process_name}可能没有响应停止命令。",
        "stop_kill": f"停止等待超过上限，正在强制终止{process_name}。",
        "force_kill": f"正在强制终止{process_name}。",
    }
    return messages.get(level, f"运行超时事件: {level}")


def _log_framework_event(state: LiveRun, text: str, tone: str) -> None:
    if tone == "danger":
        logger.error("generic run event run_id=%s kind=%s text=%s", state.id, state.kind, text)
    elif tone == "warning":
        logger.warning("generic run event run_id=%s kind=%s text=%s", state.id, state.kind, text)
    else:
        logger.info("generic run event run_id=%s kind=%s text=%s", state.id, state.kind, text)
