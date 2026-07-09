import logging
import os
import time
import json
from pathlib import Path

from linux_maa.diagnostics import Diagnostics, LogRetentionPolicy
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.run_manager.store import RunStateStore
from linux_maa.scheduler.state import SchedulerStateStore


def test_run_state_store_writes_readable_state_outside_debug(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime)
    store = RunStateStore(runtime)
    run_id = "run-1"
    log_files = diagnostics.maa_cli_log_files(run_id)
    event_log_file = diagnostics.event_log_file(run_id)

    store.create_run(
        run_id=run_id,
        kind="schedule",
        title="Daily / 04:00",
        max_retries=3,
        log_files=log_files,
        event_log_file=event_log_file,
        metadata={
            "schedule_id": "daily",
            "schedule_name": "Daily",
            "entry_id": "t0400",
            "entry_name": "04:00",
            "task_config": "General",
            "game_day": "2026-07-01",
            "trigger": "schedule",
        },
        history_scope=("schedules", "daily"),
    )
    store.add_retry(
        retry_id="run-1-1",
        run_id=run_id,
        retry_index=1,
        retry_group=1,
        status="succeeded",
        started_at="2026-07-01T04:00:00",
        updated_at="2026-07-01T04:01:00",
        ended_at="2026-07-01T04:01:00",
        return_code=0,
        metadata={"task_ids": ["startup"], "task_results": [{"task_id": "startup", "status": "succeeded"}]},
        artifacts={"generated_config_dir": "runtime/maa/generated-configs/schedule-run-1"},
        log_entries=[{"type": "block", "id": "log-1", "source": "framework:event", "kind": "event", "messages": [{"text": "开始运行"}], "lines": ["开始运行"]}],
        log_files=log_files,
    )
    store.finish_run(
        run_id,
        status="succeeded",
        retry_count=1,
        retry_group_count=1,
        metadata={"summary": {"final_status": "succeeded"}},
    )

    run = store.runs(kind="schedule", limit=1)[0]
    assert run.status == "succeeded"
    assert run.metadata["schedule_id"] == "daily"
    assert run.log_files == {
        "stdout": "debug/linux-maa/external/maa-cli/run-1.stdout.log",
        "stderr": "debug/linux-maa/external/maa-cli/run-1.stderr.log",
    }
    assert run.event_log_file == "debug/linux-maa/events/run-1.jsonl"
    assert store.retries(run_id)[0]["log_entries"][0]["kind"] == "event"
    assert store.retries(run_id)[0]["metadata"]["task_results"] == [{"task_id": "startup", "status": "succeeded"}]
    assert store.retries(run_id)[0]["artifacts"]["generated_config_dir"] == "runtime/maa/generated-configs/schedule-run-1"
    assert store.retries(run_id)[0]["log_entries_file"] == "history/linux-maa/runs/schedules/daily/run-1.json"

    recent_runs = (tmp_path / "state/linux-maa/run-history/recent-run-records.json").read_text(encoding="utf-8")
    retries = (tmp_path / "state/linux-maa/run-history/run-retries.json").read_text(encoding="utf-8")
    history = (tmp_path / "history/linux-maa/runs/schedules/daily/run-1.json").read_text(encoding="utf-8")
    assert "Recent WebUI, scheduled, maintenance, and tool run records" in recent_runs
    assert "Per-retry run index" in retries
    assert "log_entries_file" in retries
    assert "开始运行" not in retries
    assert "Durable run history with retry-scoped visible log blocks" in history
    assert "开始运行" in history
    assert json.loads(history)["run"]["status"] == "succeeded"
    assert json.loads(history)["run"]["retry_count"] == 1
    assert not (tmp_path / "debug/linux-maa/history").exists()


def test_scheduler_state_store_records_stats_and_triggers(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    scheduler_state = SchedulerStateStore(runtime)

    scheduler_state.update_daily_stats(
        schedule_id="daily",
        game_day="2026-07-01",
        task_names={"startup": "启动"},
        task_statuses={"startup": "succeeded"},
    )
    scheduler_state.mark_triggered(schedule_id="daily", entry_id="t0400", game_day="2026-07-01", run_id="run-1")

    assert scheduler_state.already_triggered(schedule_id="daily", entry_id="t0400", game_day="2026-07-01")
    assert scheduler_state.daily_stats("daily", "2026-07-01")["startup"].successes == 1
    daily_stats = (tmp_path / "state/linux-maa/scheduler/daily-task-stats.json").read_text(encoding="utf-8")
    triggers = (tmp_path / "state/linux-maa/scheduler/triggered-schedule-entries.json").read_text(encoding="utf-8")
    assert "Per-schedule daily child-task run/success counters" in daily_stats
    assert "avoid duplicate scheduled execution" in triggers


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

    tool_log_files = diagnostics.tool_log_files("tool-1")
    diagnostics.append_tool_output("tool-1", "stdout", "tool stdout\n")
    diagnostics.append_tool_output("tool-1", "stderr", "tool stderr\n")
    assert tool_log_files == {
        "stdout": "debug/linux-maa/external/tools/tool-1.stdout.log",
        "stderr": "debug/linux-maa/external/tools/tool-1.stderr.log",
    }
    assert (tmp_path / "debug/linux-maa/external/tools/tool-1.stdout.log").read_text(encoding="utf-8") == "tool stdout\n"
    assert (tmp_path / "debug/linux-maa/external/tools/tool-1.stderr.log").read_text(encoding="utf-8") == "tool stderr\n"


def test_run_state_store_records_single_attempt_for_generic_runs(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    store = RunStateStore(runtime)

    store.create_run(run_id="manual-1", kind="manual", title="General", metadata={"task": "General", "profile": "default"}, history_scope=("manual",))
    store.add_retry(
        retry_id="manual-1-1",
        run_id="manual-1",
        status="stopped",
        retry_index=1,
        retry_group=1,
        started_at="2026-07-04T01:00:00",
        updated_at="2026-07-04T01:01:00",
        ended_at="2026-07-04T01:01:00",
        return_code=1,
        metadata={"task_results": [{"type": "task", "name": "Mall", "status": "unknown"}]},
        artifacts={"generated_config_dir": "runtime/maa/generated-configs/manual-1"},
        log_entries=[{"type": "block", "id": "log-1", "source": "maa-cli:stdout", "kind": "summary", "messages": [], "lines": ["Summary"]}],
        log_files={"stdout": "debug/linux-maa/external/maa-cli/manual-1.stdout.log"},
    )
    store.finish_run(
        "manual-1",
        status="stopped",
        return_code=1,
        retry_count=1,
        retry_group_count=1,
        metadata={"summary": {"generated_config_dir": "runtime/maa/generated-configs/manual-1"}},
    )

    retry = store.retries("manual-1")[0]
    assert retry["retry_index"] == 1
    assert retry["retry_group"] == 1
    assert retry["log_entries"][0]["kind"] == "summary"
    assert retry["log_entries_file"] == "history/linux-maa/runs/manual/manual-1.json"
    history_path = tmp_path / "history/linux-maa/runs/manual/manual-1.json"
    assert history_path.is_file()
    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert history["run"]["status"] == "stopped"
    assert history["run"]["metadata"]["summary"] == {"generated_config_dir": "runtime/maa/generated-configs/manual-1"}
    assert store.run("manual-1").metadata["summary"] == {"generated_config_dir": "runtime/maa/generated-configs/manual-1"}  # type: ignore[union-attr]


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
