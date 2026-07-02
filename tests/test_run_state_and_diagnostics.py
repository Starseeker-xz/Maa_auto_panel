from pathlib import Path
import logging
import os
import time

from linux_maa.diagnostics import Diagnostics, LogRetentionPolicy
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.run_state import RunStateStore


def test_run_state_store_writes_readable_state_outside_debug(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime)
    store = RunStateStore(runtime)
    run_id = "run-1"
    log_file = diagnostics.maa_cli_log_file(run_id)
    log_files = diagnostics.maa_cli_log_files(run_id)
    event_log_file = diagnostics.event_log_file(run_id)

    store.create_run(
        run_id=run_id,
        schedule_id="daily",
        schedule_name="Daily",
        entry_id="t0400",
        entry_name="04:00",
        task_config="General",
        game_day="2026-07-01",
        trigger="schedule",
        selected_task_ids=["startup"],
        log_file=log_file,
        log_files=log_files,
        event_log_file=event_log_file,
    )
    store.add_attempt(
        attempt_id="run-1-1",
        run_id=run_id,
        attempt_index=1,
        retry_group=1,
        status="succeeded",
        started_at="2026-07-01T04:00:00",
        ended_at="2026-07-01T04:01:00",
        return_code=0,
        task_ids=["startup"],
        task_results=[{"task_id": "startup", "status": "succeeded"}],
        log_entries=[{"type": "line", "text": "开始运行"}],
        log_file=log_file,
        log_files=log_files,
        generated_config_dir="runtime/maa/generated-configs/schedule-run-1",
    )
    store.update_daily_stats(
        schedule_id="daily",
        game_day="2026-07-01",
        task_names={"startup": "启动"},
        task_statuses={"startup": "succeeded"},
    )
    store.mark_triggered(schedule_id="daily", entry_id="t0400", game_day="2026-07-01", run_id=run_id)
    store.finish_run(
        run_id,
        status="succeeded",
        attempt_count=1,
        retry_group_count=1,
        log_file=log_file,
        log_files=log_files,
        summary={"final_status": "succeeded"},
    )

    run = store.recent_runs("daily", limit=1)[0]
    assert run.status == "succeeded"
    assert run.log_file == "debug/linux-maa/external/maa-cli/run-1.stdout.log"
    assert run.log_files == {
        "stdout": "debug/linux-maa/external/maa-cli/run-1.stdout.log",
        "stderr": "debug/linux-maa/external/maa-cli/run-1.stderr.log",
    }
    assert run.event_log_file == "debug/linux-maa/events/run-1.jsonl"
    assert store.already_triggered(schedule_id="daily", entry_id="t0400", game_day="2026-07-01")
    assert store.daily_stats("daily", "2026-07-01")["startup"].successes == 1
    assert store.attempts(run_id)[0]["generated_config_dir"] == "runtime/maa/generated-configs/schedule-run-1"

    recent_runs = (tmp_path / "state/linux-maa/run-history/recent-run-records.json").read_text(encoding="utf-8")
    attempts = (tmp_path / "state/linux-maa/run-history/scheduled-run-attempts.json").read_text(encoding="utf-8")
    daily_stats = (tmp_path / "state/linux-maa/scheduler/daily-task-stats.json").read_text(encoding="utf-8")
    triggers = (tmp_path / "state/linux-maa/scheduler/triggered-schedule-entries.json").read_text(encoding="utf-8")
    assert "Recent WebUI, scheduled, and maintenance run records" in recent_runs
    assert "Per-attempt records for scheduled runs" in attempts
    assert "Per-schedule daily child-task run/success counters" in daily_stats
    assert "avoid duplicate scheduled execution" in triggers
    assert not (tmp_path / "debug/linux-maa/history").exists()


def test_diagnostics_writes_framework_and_external_logs(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime)
    logger = diagnostics.configure_logging()

    for level in [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]:
        logger.log(level, "level probe %s", logging.getLevelName(level))
    diagnostics.append_run_event("run-1", "manual", "framework", "人读事件", tone="info")
    diagnostics.append_maa_cli_output("run-1", "stdout", "stdout line\n")
    diagnostics.append_maa_cli_output("run-1", "stderr", "stderr line\n")

    framework = (tmp_path / "debug/linux-maa/framework.log").read_text(encoding="utf-8")
    assert "DEBUG" in framework
    assert "INFO" in framework
    assert "WARNING" in framework
    assert "ERROR" in framework
    assert "CRITICAL" in framework
    assert "level probe DEBUG" in framework
    assert diagnostics.run_events("run-1")[0]["text"] == "人读事件"
    assert (tmp_path / "debug/linux-maa/external/maa-cli/run-1.stdout.log").read_text(encoding="utf-8") == "stdout line\n"
    assert (tmp_path / "debug/linux-maa/external/maa-cli/run-1.stderr.log").read_text(encoding="utf-8") == "stderr line\n"


def test_diagnostics_retention_prunes_debug_artifacts(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(
        runtime,
        LogRetentionPolicy(
            max_age_days=9999,
            max_event_log_files=1,
            max_maa_cli_log_files=1,
            max_maacore_capture_files=1,
            max_generated_config_dirs=1,
            max_legacy_run_log_files=1,
            max_maacore_debug_files=1,
        ),
    )
    old_event = runtime.framework_event_log_dir / "old.jsonl"
    new_event = runtime.framework_event_log_dir / "new.jsonl"
    old_cli = runtime.maa_cli_log_dir / "old.stdout.log"
    new_cli = runtime.maa_cli_log_dir / "new.stdout.log"
    old_maacore = runtime.maacore_capture_log_dir / "old.log"
    new_maacore = runtime.maacore_capture_log_dir / "new.log"
    old_generated = runtime.generated_config_dir / "old"
    new_generated = runtime.generated_config_dir / "new"
    old_legacy = runtime.run_log_dir / "old.log"
    new_legacy = runtime.run_log_dir / "new.log"
    old_debug = runtime.state_home / "maa" / "debug" / "old.png"
    new_debug = runtime.state_home / "maa" / "debug" / "new.png"

    for path in [old_event, new_event, old_cli, new_cli, old_maacore, new_maacore, old_legacy, new_legacy, old_debug, new_debug]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(path.name, encoding="utf-8")
    for path in [old_generated, new_generated]:
        path.mkdir(parents=True, exist_ok=True)
        (path / "task.json").write_text("{}", encoding="utf-8")

    now = time.time()
    for path in [old_event, old_cli, old_maacore, old_generated, old_legacy, old_debug]:
        os.utime(path, (now - 10, now - 10))
    for path in [new_event, new_cli, new_maacore, new_generated, new_legacy, new_debug]:
        os.utime(path, (now, now))

    diagnostics.enforce_retention()

    assert not old_event.exists()
    assert new_event.exists()
    assert not old_cli.exists()
    assert new_cli.exists()
    assert not old_maacore.exists()
    assert new_maacore.exists()
    assert not old_generated.exists()
    assert new_generated.exists()
    assert not old_legacy.exists()
    assert new_legacy.exists()
    assert not old_debug.exists()
    assert new_debug.exists()
