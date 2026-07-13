from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from maa_auto_panel.logs.state import RunLogBuffer
from maa_auto_panel.process import StreamingProcessResult
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.logs import RunLogProfile
from maa_auto_panel.run_manager.state import LiveRun, RunKind, RunTimeouts
from maa_auto_panel.run_resources import RUN_PRIORITY_NORMAL, RUN_PRIORITY_VALUES, RunResource


CommandBuilder = Callable[["RunAttempt"], CommandSpec | None]
RawLineHandler = Callable[["RunAttempt", str, str], None]
AttemptCallback = Callable[["RunAttempt"], None]
StartCallback = Callable[["RunAttempt"], "RetryDecision | None"]
EvaluateAttempt = Callable[["RunAttempt", StreamingProcessResult], "RetryDecision | None"]
AfterAttempt = Callable[["RunAttempt", StreamingProcessResult, "RetryDecision"], "RetryDecision | None"]
BeforeRetry = Callable[["RunAttempt", "RetryDecision"], None]
FinishCallback = Callable[["RunCallbackAPI", "RunCompletion"], "RunCompletion | None"]
ScriptCommandBuilder = Callable[["RunAttempt"], CommandSpec | None]
LogConfigurator = Callable[[RunLogBuffer], None]
RunFinishedListener = Callable[[LiveRun], None]


@dataclass(frozen=True)
class RunTextTemplates:
    """Human-readable events for the manager-owned command loop."""

    process_name: str = "进程"
    start: str = "运行: {title}"
    retry_start: str = "开始第 {retry_index} 次重试"
    completed: str = "进程执行完成"
    exit_code: str = "进程退出码: {return_code}"
    retry_next: str = "准备重试运行。"
    retry_limit_reached: str = ""
    start_failed: str = "进程启动失败: {error}"
    stop_requested: str = "收到停止请求，正在终止进程..."
    force_stop_requested: str = "收到强制停止请求，正在强杀进程..."
    execution_failed: str = "运行失败: {error}"


@dataclass
class RetryDecision:
    """Callback decision for the just-finished attempt."""

    retry_status: str
    return_code: int | None = None
    run_status: str | None = None
    continue_retry: bool = False
    next_command: CommandSpec | None = None
    next_attempt_payload: dict[str, object] | None = None
    retry_metadata: dict[str, object] = field(default_factory=dict)
    retry_artifacts: dict[str, object] = field(default_factory=dict)
    summary_patch: dict[str, object] = field(default_factory=dict)


@dataclass
class RunCompletion:
    """Final run result assembled before persistence."""

    status: str
    return_code: int | None = None
    summary: dict[str, object] = field(default_factory=dict)
    metadata_patch: dict[str, object] = field(default_factory=dict)
    artifacts: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RunCallbacks:
    """Optional domain hooks; lifecycle and retry ownership remain in the manager."""

    on_start: StartCallback | None = None
    before_retry: BeforeRetry | None = None
    before_attempt: AttemptCallback | None = None
    build_command: CommandBuilder | None = None
    on_raw_line: RawLineHandler | None = None
    evaluate_attempt: EvaluateAttempt | None = None
    after_attempt: AfterAttempt | None = None
    on_finish: FinishCallback | None = None


@dataclass(frozen=True)
class RunScriptSpec:
    command: CommandSpec | ScriptCommandBuilder
    label: str = "script"
    source_prefix: str = "script"
    timeouts: RunTimeouts = field(default_factory=lambda: RunTimeouts(runtime_kill_seconds=120))
    log_profile: RunLogProfile | None = None


@dataclass(frozen=True)
class RunScriptHooks:
    before_run: tuple[RunScriptSpec, ...] = ()
    after_run: tuple[RunScriptSpec, ...] = ()
    before_retry: tuple[RunScriptSpec, ...] = ()
    after_retry: tuple[RunScriptSpec, ...] = ()


@dataclass(frozen=True)
class RunStartPlan:
    """Opaque run plan prepared by a domain service."""

    kind: RunKind
    title: str
    command: CommandSpec | None = None
    max_retries: int = 1
    callbacks: RunCallbacks = field(default_factory=RunCallbacks)
    timeouts: RunTimeouts = field(default_factory=RunTimeouts)
    log_profile: RunLogProfile = field(default_factory=RunLogProfile)
    script_hooks: RunScriptHooks = field(default_factory=RunScriptHooks)
    script_log_profile: RunLogProfile = field(default_factory=RunLogProfile)
    metadata: dict[str, object] = field(default_factory=dict)
    artifacts: dict[str, object] = field(default_factory=dict)
    log_files: dict[str, str] = field(default_factory=dict)
    event_log_file: str | None = None
    initial_attempt_payload: dict[str, object] = field(default_factory=dict)
    history_scope: tuple[str, ...] = ()
    resources: tuple[RunResource, ...] = ()
    priority_name: str = "normal"
    priority: int | None = None
    force_after_seconds: float | None = None
    preemptible: bool = True
    text: RunTextTemplates = field(default_factory=RunTextTemplates)

    def priority_value(self) -> int:
        return self.priority if self.priority is not None else RUN_PRIORITY_VALUES.get(self.priority_name, RUN_PRIORITY_NORMAL)
