from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from linux_maa.scheduler.models import DailyTaskStats, ScheduleEntry, TaskPolicy
from linux_maa.utils import slugify


SUCCESS_STATUS = "succeeded"


@dataclass(frozen=True)
class InitialTaskSelection:
    """Result of initial task filtering: selected task ids and skipped tasks with reasons."""
    selected: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


def task_policies_from_config(data: dict[str, object]) -> list[TaskPolicy]:
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return []

    policies: list[TaskPolicy] = []
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            continue
        metadata = task.get("linux_maa") if isinstance(task.get("linux_maa"), dict) else {}
        assert isinstance(metadata, dict)
        policies.append(
            TaskPolicy(
                id=_task_item_id(task, index),
                name=str(task.get("name") or task.get("type") or f"Task {index}"),
                type=str(task.get("type") or "Unknown"),
                important=metadata.get("important") is not False,
                unlimited_runs=metadata.get("unlimited_runs") is not False,
                min_daily_successes=_non_negative_int(metadata.get("min_daily_successes"), default=1),
                retry_even_success=metadata.get("retry_even_success") is True,
            )
        )
    return policies


def enabled_task_ids_from_config(data: dict[str, object]) -> list[str]:
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return []

    task_ids: list[str] = []
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            continue
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        assert isinstance(params, dict)
        if params.get("enable") is False:
            continue
        task_ids.append(_task_item_id(task, index))
    return task_ids


def retry_unfinished_task_ids(task_ids: list[str], attempt_status_by_task_id: dict[str, str], *, run_successful_task_ids: set[str] | None = None) -> list[str]:
    run_successful_task_ids = run_successful_task_ids or set()
    output: list[str] = []
    for task_id in task_ids:
        if task_id in run_successful_task_ids:
            continue
        if attempt_status_by_task_id.get(task_id) == SUCCESS_STATUS:
            continue
        output.append(task_id)
    return output


def initial_task_ids(
    policies: Iterable[TaskPolicy],
    entry: ScheduleEntry,
    stats: dict[str, DailyTaskStats],
) -> list[str]:
    return initial_task_selection(policies, entry, stats).selected


def initial_task_selection(
    policies: Iterable[TaskPolicy],
    entry: ScheduleEntry,
    stats: dict[str, DailyTaskStats],
) -> InitialTaskSelection:
    enabled = set(entry.task_ids)
    selected: list[str] = []
    skipped: list[dict[str, str]] = []
    for policy in policies:
        if policy.id not in enabled:
            skipped.append({"task_id": policy.id, "reason": "该时间点未启用"})
            continue
        task_stats = stats.get(policy.id, DailyTaskStats(task_id=policy.id, task_name=policy.name))
        if policy.important:
            if policy.unlimited_runs or task_stats.successes < policy.min_daily_successes:
                selected.append(policy.id)
            else:
                skipped.append(
                    {
                        "task_id": policy.id,
                        "reason": f"今日成功次数已满足 {task_stats.successes}/{policy.min_daily_successes}",
                    }
                )
            continue

        if policy.unlimited_runs or task_stats.runs < policy.min_daily_successes:
            selected.append(policy.id)
        else:
            skipped.append(
                {
                    "task_id": policy.id,
                    "reason": f"今日运行次数已满足 {task_stats.runs}/{policy.min_daily_successes}",
                }
            )
    return InitialTaskSelection(selected=selected, skipped=skipped)


def retry_task_ids(
    policies: Iterable[TaskPolicy],
    entry: ScheduleEntry,
    sorted_entries: list[ScheduleEntry],
    stats: dict[str, DailyTaskStats],
    attempt_status_by_task_id: dict[str, str],
    *,
    run_successful_task_ids: set[str] | None = None,
) -> list[str]:
    policy_list = list(policies)
    enabled = set(entry.task_ids)
    run_successful_task_ids = run_successful_task_ids or set()
    retry_causes: set[str] = set()
    rerun_on_retry: set[str] = set()
    for policy in policy_list:
        if policy.id not in enabled or not policy.important:
            continue
        status = attempt_status_by_task_id.get(policy.id, "missing")
        already_succeeded = policy.id in run_successful_task_ids
        if policy.retry_even_success:
            rerun_on_retry.add(policy.id)
            if status == SUCCESS_STATUS:
                continue
        if status == SUCCESS_STATUS:
            continue
        if status == "missing" and already_succeeded:
            continue
        if policy.unlimited_runs:
            retry_causes.add(policy.id)
            continue

        task_stats = stats.get(policy.id, DailyTaskStats(task_id=policy.id, task_name=policy.name))
        remaining_successes = max(0, policy.min_daily_successes - task_stats.successes)
        if remaining_successes <= 0:
            continue
        remaining_slots = remaining_enabled_slots(sorted_entries, current_entry_id=entry.id, task_id=policy.id)
        if remaining_slots <= remaining_successes:
            retry_causes.add(policy.id)
    if not retry_causes:
        return []
    selected = rerun_on_retry | retry_causes
    return [policy.id for policy in policy_list if policy.id in selected]


def remaining_enabled_slots(sorted_entries: list[ScheduleEntry], *, current_entry_id: str, task_id: str) -> int:
    try:
        start_index = next(index for index, entry in enumerate(sorted_entries) if entry.id == current_entry_id)
    except StopIteration:
        start_index = 0
    return sum(1 for entry in sorted_entries[start_index:] if entry.enabled and task_id in entry.task_ids)


def _non_negative_int(value: object, *, default: int) -> int:
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _task_item_id(task: dict[str, object], index: int) -> str:
    metadata = task.get("linux_maa")
    explicit = metadata.get("id") if isinstance(metadata, dict) else None
    if isinstance(explicit, str) and explicit.strip():
        return slugify(explicit) or f"task-{index}"
    task_type = str(task.get("type") or "Task")
    name = task.get("name")
    base = f"{task_type}-{name}" if isinstance(name, str) and name.strip() else task_type
    return slugify(base) or f"task-{index}"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
