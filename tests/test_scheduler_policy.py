from datetime import datetime
from zoneinfo import ZoneInfo

from linux_maa.scheduler.models import DailyTaskStats, ScheduleEntry, TaskPolicy
from linux_maa.scheduler.policy import initial_task_selection, retry_task_ids
from linux_maa.scheduler.time import game_day_info


def test_cn_server_game_day_order_in_london_summer_time() -> None:
    entries = [
        ScheduleEntry(id="t0400", name="04", time="04:00", task_ids=[]),
        ScheduleEntry(id="t0800", name="08", time="08:00", task_ids=[]),
        ScheduleEntry(id="t1600", name="16", time="16:00", task_ids=[]),
        ScheduleEntry(id="t2200", name="22", time="22:00", task_ids=[]),
    ]

    info = game_day_info(
        entries,
        client="Bilibili",
        timezone_name="Europe/London",
        now=datetime(2026, 6, 30, 12, 0, tzinfo=ZoneInfo("Europe/London")),
    )

    assert info.reset_local_time == "21:00"
    assert info.order == ["t2200", "t0400", "t0800", "t1600"]


def test_min_daily_success_retry_only_when_remaining_slots_are_tight() -> None:
    recruit = TaskPolicy(
        id="recruit",
        name="公招",
        type="Recruit",
        important=True,
        unlimited_runs=False,
        min_daily_successes=2,
    )
    entries = [
        ScheduleEntry(id="t2200", name="22", time="22:00", task_ids=["recruit"]),
        ScheduleEntry(id="t0400", name="04", time="04:00", task_ids=["recruit"]),
        ScheduleEntry(id="t0800", name="08", time="08:00", task_ids=["recruit"]),
        ScheduleEntry(id="t1600", name="16", time="16:00", task_ids=["recruit"]),
    ]
    stats = {"recruit": DailyTaskStats(task_id="recruit", task_name="公招", successes=1, runs=3)}

    assert retry_task_ids([recruit], entries[1], entries, stats, {"recruit": "failed"}) == []
    assert retry_task_ids([recruit], entries[2], entries, stats, {"recruit": "failed"}) == []
    assert retry_task_ids([recruit], entries[3], entries, stats, {"recruit": "failed"}) == ["recruit"]


def test_retry_even_success_only_reruns_when_retry_exists() -> None:
    startup = TaskPolicy(
        id="startup",
        name="启动",
        type="StartUp",
        important=True,
        unlimited_runs=True,
        retry_even_success=True,
    )
    award = TaskPolicy(
        id="award",
        name="奖励",
        type="Award",
        important=True,
        unlimited_runs=True,
    )
    entry = ScheduleEntry(id="t0400", name="04", time="04:00", task_ids=["startup", "award"])
    stats: dict[str, DailyTaskStats] = {}

    assert retry_task_ids([startup, award], entry, [entry], stats, {"startup": "succeeded", "award": "succeeded"}) == []
    assert retry_task_ids([startup, award], entry, [entry], stats, {"startup": "succeeded", "award": "failed"}) == ["startup", "award"]


def test_retry_keeps_original_policy_order() -> None:
    startup = TaskPolicy(
        id="startup",
        name="启动",
        type="StartUp",
        important=True,
        unlimited_runs=True,
        retry_even_success=True,
    )
    recruit = TaskPolicy(
        id="recruit",
        name="公招",
        type="Recruit",
        important=True,
        unlimited_runs=True,
    )
    closedown = TaskPolicy(
        id="closedown",
        name="关闭",
        type="CloseDown",
        important=True,
        unlimited_runs=True,
        retry_even_success=True,
    )
    entry = ScheduleEntry(id="t0400", name="04", time="04:00", task_ids=["startup", "recruit", "closedown"])

    assert retry_task_ids([startup, recruit, closedown], entry, [entry], {}, {"startup": "succeeded", "recruit": "failed", "closedown": "succeeded"}) == [
        "startup",
        "recruit",
        "closedown",
    ]


def test_retry_does_not_requeue_already_successful_missing_tasks() -> None:
    startup = TaskPolicy(
        id="startup",
        name="启动",
        type="StartUp",
        important=True,
        unlimited_runs=True,
        retry_even_success=True,
    )
    award = TaskPolicy(
        id="award",
        name="奖励",
        type="Award",
        important=True,
        unlimited_runs=True,
    )
    recruit = TaskPolicy(
        id="recruit",
        name="公招",
        type="Recruit",
        important=True,
        unlimited_runs=True,
    )
    closedown = TaskPolicy(
        id="closedown",
        name="关闭",
        type="CloseDown",
        important=True,
        unlimited_runs=True,
        retry_even_success=True,
    )
    entry = ScheduleEntry(id="t0400", name="04", time="04:00", task_ids=["startup", "award", "recruit", "closedown"])

    assert retry_task_ids(
        [startup, award, recruit, closedown],
        entry,
        [entry],
        {},
        {"startup": "succeeded", "recruit": "failed", "closedown": "succeeded"},
        run_successful_task_ids={"startup", "award", "closedown"},
    ) == ["startup", "recruit", "closedown"]


def test_initial_selection_reports_skipped_threshold_reason() -> None:
    annihilation = TaskPolicy(
        id="fight-a",
        name="剿灭",
        type="Fight",
        important=True,
        unlimited_runs=False,
        min_daily_successes=1,
    )
    farming = TaskPolicy(
        id="fight-b",
        name="刷理智",
        type="Fight",
        important=True,
        unlimited_runs=False,
        min_daily_successes=3,
    )
    entry = ScheduleEntry(id="t1600", name="16", time="16:00", task_ids=["fight-a", "fight-b"])
    stats = {
        "fight-a": DailyTaskStats(task_id="fight-a", task_name="剿灭", successes=1, runs=1),
        "fight-b": DailyTaskStats(task_id="fight-b", task_name="刷理智", successes=1, runs=1),
    }

    selection = initial_task_selection([annihilation, farming], entry, stats)

    assert selection.selected == ["fight-b"]
    assert selection.skipped == [
        {"task_id": "fight-a", "reason": "今日成功次数已满足 1/1"},
    ]
