from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from maa_auto_panel.logs.records import LogMessage
from maa_auto_panel.logs.state import RunLogBuffer
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.state import LiveRetry, LiveRun, RunKind

if TYPE_CHECKING:
    from maa_auto_panel.run_manager.contracts import RunStartPlan
    from maa_auto_panel.run_manager.manager import GenericRunManager


@dataclass
class RetryDecision:
    """Domain decision for the just-finished retry."""

    retry_status: str
    return_code: int | None = None
    run_status: str | None = None
    continue_retry: bool = False
    next_command: CommandSpec | None = None
    next_retry_payload: dict[str, object] | None = None
    retry_metadata: dict[str, object] = field(default_factory=dict)
    retry_artifacts: dict[str, object] = field(default_factory=dict)
    retry_summary_messages: list[LogMessage] = field(default_factory=list)
    summary_patch: dict[str, object] = field(default_factory=dict)


class RunCallbackAPI:
    """Small callback facade for events and stop-aware waits; lifecycle stays internal."""

    def __init__(
        self,
        manager: GenericRunManager,
        state: LiveRun,
        plan: RunStartPlan,
        retry: LiveRetry | None = None,
    ) -> None:
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

    def configure_log(self, callback: Callable[[RunLogBuffer], None]) -> None:
        if self._retry is None:
            return
        callback(self._retry.log)
        self._manager.mark_updated(self._state, self._retry)

    def mark_updated(self) -> None:
        self._manager.mark_updated(self._state, self._retry)


@dataclass(frozen=True)
class RetryContext:
    """Read-only retry view passed to callbacks."""

    api: RunCallbackAPI
    run_id: str
    retry_id: str
    retry_index: int
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

    def configure_log(self, callback: Callable[[RunLogBuffer], None]) -> None:
        self.api.configure_log(callback)

    def mark_updated(self) -> None:
        self.api.mark_updated()
