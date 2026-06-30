from linux_maa.scheduler.models import DailyTaskStats, ScheduleEntry, TaskPolicy
from linux_maa.scheduler.service import _final_status


def test_final_status_allows_unmet_daily_threshold_after_current_success() -> None:
    startup = TaskPolicy(
        id="startup",
        name="启动",
        type="StartUp",
        important=True,
        unlimited_runs=True,
    )
    fight = TaskPolicy(
        id="fight",
        name="刷理智",
        type="Fight",
        important=True,
        unlimited_runs=False,
        min_daily_successes=3,
    )
    recruit = TaskPolicy(
        id="recruit",
        name="公招",
        type="Recruit",
        important=True,
        unlimited_runs=False,
        min_daily_successes=2,
    )
    closedown = TaskPolicy(
        id="closedown",
        name="关闭",
        type="CloseDown",
        important=True,
        unlimited_runs=True,
    )
    entry = ScheduleEntry(id="t1600", name="16", time="16:00", task_ids=["startup", "fight", "recruit", "closedown"])
    stats = {
        "fight": DailyTaskStats(task_id="fight", task_name="刷理智", successes=2, runs=4),
        "recruit": DailyTaskStats(task_id="recruit", task_name="公招", successes=1, runs=6),
    }

    assert (
        _final_status(
            [startup, fight, recruit, closedown],
            entry,
            stats,
            {"startup": "succeeded", "recruit": "succeeded", "closedown": "succeeded"},
            {"startup", "fight", "recruit", "closedown"},
        )
        == "succeeded"
    )


def test_final_status_still_fails_unlimited_task_without_current_success() -> None:
    startup = TaskPolicy(
        id="startup",
        name="启动",
        type="StartUp",
        important=True,
        unlimited_runs=True,
    )
    entry = ScheduleEntry(id="t1600", name="16", time="16:00", task_ids=["startup"])

    assert _final_status([startup], entry, {}, {"startup": "failed"}, set()) == "failed"
