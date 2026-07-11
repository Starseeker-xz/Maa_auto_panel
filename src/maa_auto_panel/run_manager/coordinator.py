from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from maa_auto_panel.diagnostics import get_logger
from maa_auto_panel.run_resources import RunResource, resources_conflict

logger = get_logger(__name__)

ResourceCallback = Callable[[], None]


@dataclass
class RunLease:
    """Global resource claim for a run, with callbacks into that run's own stop controls."""

    run_id: str
    kind: str
    title: str
    priority: int
    resources: tuple[RunResource, ...] = ()
    request_stop: ResourceCallback | None = None
    request_force_stop: ResourceCallback | None = None
    force_after_seconds: float | None = None
    preempt_stop_requested_at: float | None = field(default=None, init=False)
    preempt_force_requested: bool = field(default=False, init=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "title": self.title,
            "priority": self.priority,
            "resources": [resource.to_dict() for resource in self.resources],
        }


class RunConflictError(RuntimeError):
    """Raised when a new run loses a resource conflict to a higher-priority run."""

    def __init__(self, lease: RunLease, blockers: list[RunLease]) -> None:
        self.lease = lease
        self.blockers = blockers
        blocker_text = ", ".join(f"{item.title}({item.run_id})" for item in blockers)
        super().__init__(f"运行资源被更高优先级运行占用: {blocker_text}")


class RunCoordinator:
    """Coordinates global live-run resource claims and priority conflict handling."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._leases: dict[str, RunLease] = {}
        self._closing = False

    def acquire(self, lease: RunLease) -> None:
        if not lease.resources:
            return

        while True:
            callbacks: list[ResourceCallback] = []
            wait_timeout = 1.0
            with self._condition:
                if self._closing:
                    raise RuntimeError("Application is shutting down")
                conflicts = self._conflicts_locked(lease)
                if not conflicts:
                    self._leases[lease.run_id] = lease
                    self._condition.notify_all()
                    logger.info(
                        "run resources acquired run_id=%s priority=%s resources=%s",
                        lease.run_id,
                        lease.priority,
                        [resource.to_dict() for resource in lease.resources],
                    )
                    return

                blockers = [item for item in conflicts if item.priority > lease.priority]
                if blockers:
                    raise RunConflictError(lease, blockers)

                now = time.monotonic()
                for item in conflicts:
                    if item.priority < lease.priority:
                        callback = self._preemption_callback_locked(item, now)
                        if callback is not None:
                            callbacks.append(callback)
                        force_wait = self._force_wait_seconds_locked(item, now)
                        if force_wait is not None:
                            wait_timeout = min(wait_timeout, force_wait)

            for callback in callbacks:
                try:
                    callback()
                except Exception:
                    logger.exception("run preemption callback failed")

            with self._condition:
                self._condition.wait(timeout=max(0.05, wait_timeout))

    def begin_shutdown(self) -> None:
        with self._condition:
            self._closing = True
            self._condition.notify_all()

    def release(self, run_id: str) -> None:
        with self._condition:
            lease = self._leases.pop(run_id, None)
            if lease is not None:
                logger.info("run resources released run_id=%s", run_id)
            self._condition.notify_all()

    def occupied_resources(self) -> list[dict[str, object]]:
        with self._lock:
            return [lease.to_dict() for lease in self._leases.values()]

    def _conflicts_locked(self, lease: RunLease) -> list[RunLease]:
        return [
            active
            for active in self._leases.values()
            if active.run_id != lease.run_id and any(resources_conflict(candidate, current) for candidate in lease.resources for current in active.resources)
        ]

    def _preemption_callback_locked(self, lease: RunLease, now: float) -> ResourceCallback | None:
        if lease.preempt_stop_requested_at is None:
            lease.preempt_stop_requested_at = now
            logger.warning("run preemption stop requested run_id=%s title=%s", lease.run_id, lease.title)
            return lease.request_stop
        if (
            lease.force_after_seconds
            and lease.request_force_stop is not None
            and not lease.preempt_force_requested
            and now - lease.preempt_stop_requested_at >= lease.force_after_seconds
        ):
            lease.preempt_force_requested = True
            logger.warning("run preemption force-stop requested run_id=%s title=%s", lease.run_id, lease.title)
            return lease.request_force_stop
        return None

    def _force_wait_seconds_locked(self, lease: RunLease, now: float) -> float | None:
        if not lease.force_after_seconds or lease.preempt_stop_requested_at is None or lease.preempt_force_requested:
            return None
        return max(0.05, lease.force_after_seconds - (now - lease.preempt_stop_requested_at))
