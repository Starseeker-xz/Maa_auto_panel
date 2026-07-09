from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any, Literal

from linux_maa.logs.state import RunLogBuffer
from linux_maa.time_utils import server_now_iso


RunKind = str
RunStatus = Literal["idle", "running", "stopping", "succeeded", "failed", "soft_failed", "stopped", "skipped"]


@dataclass(frozen=True)
class RunTimeouts:
    """Generic timeout thresholds used by all process-backed runs."""

    no_output_warning_seconds: int = 0
    no_output_kill_seconds: int = 0
    runtime_warning_seconds: int = 0
    runtime_kill_seconds: int = 0
    stop_warning_seconds: int = 0
    stop_kill_seconds: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "no_output_warning_seconds": self.no_output_warning_seconds,
            "no_output_kill_seconds": self.no_output_kill_seconds,
            "runtime_warning_seconds": self.runtime_warning_seconds,
            "runtime_kill_seconds": self.runtime_kill_seconds,
            "stop_warning_seconds": self.stop_warning_seconds,
            "stop_kill_seconds": self.stop_kill_seconds,
        }


@dataclass
class LiveRetry:
    """One retry segment within a run. Only the current retry remains mutable."""

    id: str
    run_id: str
    retry_index: int
    retry_group: int
    started_at: str
    updated_at: str
    status: str = "running"
    ended_at: str | None = None
    return_code: int | None = None
    log_files: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    closed: bool = False
    log: RunLogBuffer = field(default_factory=RunLogBuffer)

    def touch(self) -> None:
        self.updated_at = now_text()

    def seal(self, *, status: str, return_code: int | None) -> None:
        self.log.flush()
        self.status = status
        self.return_code = return_code
        self.ended_at = now_text()
        self.updated_at = self.ended_at
        self.closed = True

    def to_dict(self, *, include_logs: bool = True) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "run_id": self.run_id,
            "retry_index": self.retry_index,
            "retry_group": self.retry_group,
            "status": self.status,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "ended_at": self.ended_at,
            "return_code": self.return_code,
            "log_files": dict(self.log_files),
            "metadata": dict(self.metadata),
            "artifacts": dict(self.artifacts),
            "closed": self.closed,
        }
        if include_logs:
            data["log_entries"] = self.log.entries()
        return data


@dataclass
class LiveRun:
    """Common live run state exposed by manual, scheduled, tool, and maintenance runners."""

    id: str
    kind: RunKind
    title: str
    status: str
    started_at: str
    updated_at: str
    max_retries: int = 1
    ended_at: str | None = None
    return_code: int | None = None
    log_files: dict[str, str] = field(default_factory=dict)
    event_log_file: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    retries: list[LiveRetry] = field(default_factory=list)
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    thread: threading.Thread | None = field(default=None, repr=False)
    stop_requested: bool = False
    force_stop_requested: bool = False
    stop_requested_at: str | None = None

    def touch(self) -> None:
        self.updated_at = now_text()

    @property
    def current_retry(self) -> LiveRetry | None:
        return self.retries[-1] if self.retries and not self.retries[-1].closed else None

    def begin_retry(
        self,
        *,
        retry_group: int = 1,
        log_files: dict[str, str] | None = None,
        log: RunLogBuffer | None = None,
    ) -> LiveRetry:
        started_at = now_text()
        retry = LiveRetry(
            id=f"{self.id}-{len(self.retries) + 1}",
            run_id=self.id,
            retry_index=len(self.retries) + 1,
            retry_group=retry_group,
            started_at=started_at,
            updated_at=started_at,
            log_files=log_files or self.log_files,
            log=log or RunLogBuffer(),
        )
        self.retries.append(retry)
        self.touch()
        return retry

    def request_stop(self) -> None:
        if self.status not in {"running", "stopping"}:
            return
        self.stop_requested = True
        if self.status == "running":
            self.status = "stopping"
        if self.stop_requested_at is None:
            self.stop_requested_at = now_text()
        self.touch()

    def request_force_stop(self) -> None:
        if self.status not in {"running", "stopping"}:
            return
        self.stop_requested = True
        self.force_stop_requested = True
        self.status = "stopping"
        if self.stop_requested_at is None:
            self.stop_requested_at = now_text()
        self.touch()

    def finish(self, *, status: str, return_code: int | None) -> None:
        self.status = status
        self.return_code = return_code
        self.process = None
        self.ended_at = now_text()
        self.updated_at = self.ended_at

    def run_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "ended_at": self.ended_at,
            "return_code": self.return_code,
            "max_retries": self.max_retries,
            "retry_count": len(self.retries),
            "retry_group_count": max((retry.retry_group for retry in self.retries), default=0),
            "log_files": dict(self.log_files),
            "event_log_file": self.event_log_file,
            "stop_requested": self.stop_requested,
            "force_stop_requested": self.force_stop_requested,
            "metadata": dict(self.metadata),
            "artifacts": dict(self.artifacts),
        }
        return data

    def to_dict(self, *, include_logs: bool = True) -> dict[str, object]:
        return {
            "run": self.run_dict(),
            "retries": [retry.to_dict(include_logs=include_logs) for retry in self.retries],
        }


def now_text() -> str:
    return server_now_iso()
