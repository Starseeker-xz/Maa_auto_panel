from maa_auto_panel.scheduler.models import DailyTaskStats, ScheduleEntry, TaskPolicy
from maa_auto_panel.scheduler.service import _final_status


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
    entries = [entry]
    stats = {
        "fight": DailyTaskStats(task_id="fight", task_name="刷理智", successes=2, runs=4),
        "recruit": DailyTaskStats(task_id="recruit", task_name="公招", successes=1, runs=6),
    }

    assert (
        _final_status(
            [startup, fight, recruit, closedown],
            entry,
            entries,
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

    assert _final_status([startup], entry, [entry], {}, {"startup": "failed"}, set()) == "failed"


def test_final_status_defers_unmet_important_threshold_when_future_slots_remain() -> None:
    annihilation = TaskPolicy(
        id="annihilation",
        name="剿灭",
        type="Fight",
        important=True,
        unlimited_runs=False,
        min_daily_successes=1,
    )
    entries = [
        ScheduleEntry(id="t2200", name="22", time="22:00", task_ids=["annihilation"]),
        ScheduleEntry(id="t0400", name="04", time="04:00", task_ids=["annihilation"]),
        ScheduleEntry(id="t0800", name="08", time="08:00", task_ids=["annihilation"]),
    ]
    stats = {"annihilation": DailyTaskStats(task_id="annihilation", task_name="剿灭", successes=0, runs=1)}

    assert _final_status([annihilation], entries[0], entries, stats, {"annihilation": "failed"}, set()) == "succeeded"
    assert _final_status([annihilation], entries[2], entries, stats, {"annihilation": "failed"}, set()) == "failed"
