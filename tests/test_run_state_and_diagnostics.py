import logging
import os
import time
import json
from pathlib import Path

import pytest

from maa_auto_panel.diagnostics import Diagnostics, LogRetentionPolicy
from maa_auto_panel.errors import CorruptState
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.store import RunStateStore, StateRetentionPolicy
from maa_auto_panel.scheduler.state import SchedulerStateStore


def test_run_state_store_rejects_corrupt_index_without_overwriting_it(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    store = RunStateStore(runtime.layout.framework, runtime.path_references)
    corrupt = store.run_records_path
    corrupt.write_text('{"runs": [', encoding="utf-8")

    with pytest.raises(CorruptState, match="Invalid JSON object"):
        store.create_run(run_id="new-run", kind="manual", title="must not overwrite")

    assert corrupt.read_text(encoding="utf-8") == '{"runs": ['


def test_run_state_store_writes_readable_state_outside_debug(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime.layout.framework, runtime.path_references)
    store = RunStateStore(runtime.layout.framework, runtime.path_references)
    run_id = "run-1"
    log_files = diagnostics.stream_log_files("maa-cli", run_id)
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
        artifacts={"generated_config_dir": "runtime:maa/generated-configs/schedule-run-1"},
        log_entries=[{"type": "block", "id": "log-1", "source": "framework:event", "kind": "event", "messages": [{"text": "开始运行"}], "lines": ["开始运行"]}],
        summary_messages=[{"text": "重试结果：✔️ 启动", "tone": "success"}],
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
        "stdout": "framework:debug/framework/external/maa-cli/run-1.stdout.log",
        "stderr": "framework:debug/framework/external/maa-cli/run-1.stderr.log",
    }
    assert run.event_log_file == "framework:debug/framework/events/run-1.jsonl"
    assert store.retries(run_id)[0]["log_entries"][0]["kind"] == "event"
    assert store.retries(run_id)[0]["metadata"]["task_results"] == [{"task_id": "startup", "status": "succeeded"}]
    assert store.retries(run_id)[0]["artifacts"]["generated_config_dir"] == "runtime:maa/generated-configs/schedule-run-1"
    assert store.retries(run_id)[0]["summary_messages"] == [{"text": "重试结果：✔️ 启动", "tone": "success"}]
    assert store.retries(run_id)[0]["log_entries_file"] == "framework:history/framework/runs/schedules/daily/run-1.json"

    recent_runs = (tmp_path / "data/state/framework/run-history/recent-run-records.json").read_text(encoding="utf-8")
    retries = (tmp_path / "data/state/framework/run-history/run-retries.json").read_text(encoding="utf-8")
    history = (tmp_path / "data/history/framework/runs/schedules/daily/run-1.json").read_text(encoding="utf-8")
    assert "Recent WebUI, scheduled, maintenance, and tool run records" in recent_runs
    assert "Per-retry run index" in retries
    assert "log_entries_file" in retries
    assert "开始运行" not in retries
    assert "Durable run history with retry-scoped visible log blocks" in history
    assert "开始运行" in history
    assert json.loads(history)["run"]["status"] == "succeeded"
    assert json.loads(history)["run"]["retry_count"] == 1
    assert json.loads(history)["retries"][0]["summary_messages"] == [{"text": "重试结果：✔️ 启动", "tone": "success"}]
    assert not (tmp_path / "data/debug/framework/history").exists()


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
    daily_stats = (tmp_path / "data/state/framework/scheduler/daily-task-stats.json").read_text(encoding="utf-8")
    triggers = (tmp_path / "data/state/framework/scheduler/triggered-schedule-entries.json").read_text(encoding="utf-8")
    assert "Per-schedule daily child-task run/success counters" in daily_stats
    assert "avoid duplicate scheduled execution" in triggers


def test_diagnostics_writes_framework_and_external_logs(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime.layout.framework, runtime.path_references)
    logger = diagnostics.configure_logging()

    for level in [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]:
        logger.log(level, "level probe %s", logging.getLevelName(level))
    diagnostics.append_run_event("run-1", "manual", "framework", "人读事件", tone="info")
    diagnostics.stream_sink("maa-cli")("run-1", "stdout", "stdout line\n")
    diagnostics.stream_sink("maa-cli")("run-1", "stderr", "stderr line\n")

    framework = (tmp_path / "data/debug/framework/framework.log").read_text(encoding="utf-8")
    assert "DEBUG" in framework
    assert "INFO" in framework
    assert "WARNING" in framework
    assert "ERROR" in framework
    assert "CRITICAL" in framework
    assert "level probe DEBUG" in framework
    assert diagnostics.run_events("run-1")[0]["text"] == "人读事件"
    assert (tmp_path / "data/debug/framework/external/maa-cli/run-1.stdout.log").read_text(encoding="utf-8") == "stdout line\n"
    assert (tmp_path / "data/debug/framework/external/maa-cli/run-1.stderr.log").read_text(encoding="utf-8") == "stderr line\n"

    tool_log_files = diagnostics.stream_log_files("tools", "tool-1")
    diagnostics.stream_sink("tools")("tool-1", "stdout", "tool stdout\n")
    diagnostics.stream_sink("tools")("tool-1", "stderr", "tool stderr\n")
    assert tool_log_files == {
        "stdout": "framework:debug/framework/external/tools/tool-1.stdout.log",
        "stderr": "framework:debug/framework/external/tools/tool-1.stderr.log",
    }
    assert (tmp_path / "data/debug/framework/external/tools/tool-1.stdout.log").read_text(encoding="utf-8") == "tool stdout\n"
    assert (tmp_path / "data/debug/framework/external/tools/tool-1.stderr.log").read_text(encoding="utf-8") == "tool stderr\n"


def test_diagnostics_captures_binary_file_increment_and_reports_next_offset(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime.layout.framework, runtime.path_references)
    source = tmp_path / "source.log"
    source.write_bytes(b"before\n")
    start_offset = source.stat().st_size
    source.write_bytes(b"before\nnew:\xff\n")

    capture = diagnostics.capture_file_increment(source, start_offset, capture_id="attempt-1")

    assert capture.log_file == "framework:debug/framework/external/incremental/attempt-1.log"
    assert capture.next_offset == source.stat().st_size
    assert capture.captured_bytes == len(b"new:\xff\n")
    assert runtime.path_references.resolve(capture.log_file).read_bytes() == b"new:\xff\n"

    empty = diagnostics.capture_file_increment(source, capture.next_offset, capture_id="attempt-2")
    assert empty.log_file is None
    assert empty.next_offset == capture.next_offset
    assert empty.captured_bytes == 0


def test_diagnostics_increment_capture_handles_missing_and_truncated_source(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime.layout.framework, runtime.path_references)
    source = tmp_path / "source.log"

    missing = diagnostics.capture_file_increment(source, 100, capture_id="missing")
    assert missing.log_file is None
    assert missing.next_offset == 0
    assert missing.captured_bytes == 0

    source.write_bytes(b"replacement")
    truncated = diagnostics.capture_file_increment(source, 100, capture_id="truncated")
    assert truncated.next_offset == len(b"replacement")
    assert truncated.captured_bytes == len(b"replacement")
    assert runtime.path_references.resolve(truncated.log_file).read_bytes() == b"replacement"


def test_run_state_store_records_single_attempt_for_generic_runs(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    store = RunStateStore(runtime.layout.framework, runtime.path_references)

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
        artifacts={"generated_config_dir": "runtime:maa/generated-configs/manual-1"},
        log_entries=[{"type": "block", "id": "log-1", "source": "maa-cli:stdout", "kind": "summary", "messages": [], "lines": ["Summary"]}],
        log_files={"stdout": "framework:debug/framework/external/maa-cli/manual-1.stdout.log"},
    )
    store.finish_run(
        "manual-1",
        status="stopped",
        return_code=1,
        retry_count=1,
        retry_group_count=1,
        metadata={"summary": {"generated_config_dir": "runtime:maa/generated-configs/manual-1"}},
    )

    retry = store.retries("manual-1")[0]
    assert retry["retry_index"] == 1
    assert retry["retry_group"] == 1
    assert retry["log_entries"][0]["kind"] == "summary"
    assert retry["log_entries_file"] == "framework:history/framework/runs/manual/manual-1.json"
    history_path = tmp_path / "data/history/framework/runs/manual/manual-1.json"
    assert history_path.is_file()
    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert history["run"]["status"] == "stopped"
    assert history["run"]["metadata"]["summary"] == {"generated_config_dir": "runtime:maa/generated-configs/manual-1"}
    assert store.run("manual-1").metadata["summary"] == {"generated_config_dir": "runtime:maa/generated-configs/manual-1"}  # type: ignore[union-attr]


def test_diagnostics_retention_prunes_debug_artifacts(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(
        runtime.layout.framework,
        runtime.path_references,
        LogRetentionPolicy(
            max_age_days=9999,
            max_event_log_files=1,
            max_stream_log_files_per_channel=1,
            max_incremental_log_files=1,
        ),
    )
    old_event = runtime.framework_event_log_dir / "old.jsonl"
    new_event = runtime.framework_event_log_dir / "new.jsonl"
    old_cli = runtime.maa_cli_log_dir / "old.stdout.log"
    new_cli = runtime.maa_cli_log_dir / "new.stdout.log"
    old_incremental = runtime.framework_external_log_dir / "incremental" / "old.log"
    new_incremental = runtime.framework_external_log_dir / "incremental" / "new.log"
    for path in [old_event, new_event, old_cli, new_cli, old_incremental, new_incremental]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(path.name, encoding="utf-8")

    now = time.time()
    for path in [old_event, old_cli, old_incremental]:
        os.utime(path, (now - 10, now - 10))
    for path in [new_event, new_cli, new_incremental]:
        os.utime(path, (now, now))

    diagnostics.enforce_retention()

    assert not old_event.exists()
    assert new_event.exists()
    assert not old_cli.exists()
    assert new_cli.exists()
    assert not old_incremental.exists()
    assert new_incremental.exists()


def test_run_aware_retention_cascades_only_owned_run_data(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    store = RunStateStore(runtime.layout.framework, runtime.path_references, StateRetentionPolicy(max_run_records=10, max_retry_records=1))
    diagnostics = Diagnostics(runtime.layout.framework, runtime.path_references)

    def add_run(run_id: str, generated_name: str) -> tuple[Path, Path, Path]:
        event_ref = diagnostics.event_log_file(run_id)
        log_refs = diagnostics.stream_log_files("maa-cli", run_id)
        diagnostics.append_run_event(run_id, "manual", "framework", "event")
        diagnostics.stream_sink("maa-cli")(run_id, "stdout", "output")
        generated = runtime.generated_config_dir / generated_name
        generated.mkdir(parents=True)
        (generated / "task.json").write_text("{}", encoding="utf-8")
        shared = tmp_path / f"{run_id}-shared.txt"
        shared.write_text("shared", encoding="utf-8")
        store.create_run(
            run_id=run_id,
            kind="manual",
            title=run_id,
            event_log_file=event_ref,
            log_files=log_refs,
            artifacts={
                "generated_config_dir": runtime.path_references.reference("runtime", generated),
                "shared_report": str(shared),
            },
            history_scope=("manual",),
        )
        store.add_retry(
            retry_id=f"{run_id}-1",
            run_id=run_id,
            retry_index=1,
            retry_group=1,
            status="succeeded",
            started_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:01Z",
            ended_at="2026-01-01T00:00:01Z",
            return_code=0,
            metadata={},
            artifacts={},
            log_entries=[],
            log_files=log_refs,
        )
        store.finish_run(run_id, status="succeeded", retry_count=1)
        return runtime.path_references.resolve(event_ref), runtime.path_references.resolve(log_refs["stdout"]), shared

    old_event, old_log, old_shared = add_run("old-run", "old-run")
    old_history = runtime.run_history_dir / "manual" / "old-run.json"
    add_run("new-run", "new-run")

    deleted = store.enforce_retention()
    orphan = runtime.framework_event_log_dir / "orphan.jsonl"
    orphan.write_text("orphan", encoding="utf-8")
    diagnostics.enforce_retention(protected_paths=store.owned_paths())

    assert [item["id"] for item in deleted] == ["old-run"]
    assert store.run("old-run") is None
    assert store.run("new-run") is not None
    assert not old_event.exists()
    assert not old_log.exists()
    assert not old_history.exists()
    assert not (runtime.generated_config_dir / "old-run").exists()
    assert old_shared.exists()
    assert not orphan.exists()
    assert runtime.path_references.resolve(diagnostics.event_log_file("new-run")).exists()
    assert [retry["id"] for retry in store.retries("new-run")] == ["new-run-1"]


def test_manual_run_delete_cascades_diagnostics_history_and_owned_artifacts(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    store = RunStateStore(runtime.layout.framework, runtime.path_references)
    diagnostics = Diagnostics(runtime.layout.framework, runtime.path_references)
    event_ref = diagnostics.event_log_file("delete-me")
    log_refs = diagnostics.stream_log_files("tools", "delete-me")
    diagnostics.append_run_event("delete-me", "tool", "framework", "event")
    diagnostics.stream_sink("tools")("delete-me", "stderr", "failure")
    generated = runtime.generated_config_dir / "delete-me"
    generated.mkdir(parents=True)
    store.create_run(
        run_id="delete-me",
        kind="tool",
        title="delete-me",
        event_log_file=event_ref,
        log_files=log_refs,
        artifacts={"generated_config_dir": runtime.path_references.reference("runtime", generated)},
        history_scope=("tools",),
    )
    store.add_retry(
        retry_id="delete-me-1", run_id="delete-me", retry_index=1, retry_group=1,
        status="failed", started_at="a", updated_at="b", ended_at="b", return_code=1,
        metadata={}, artifacts={}, log_entries=[], log_files=log_refs,
    )
    store.finish_run("delete-me", status="failed", retry_count=1)

    result = store.delete_run("delete-me")

    assert result["history_deleted"] is True
    assert not runtime.path_references.resolve(event_ref).exists()
    assert not runtime.path_references.resolve(log_refs["stderr"]).exists()
    assert not generated.exists()
    assert store.retries("delete-me") == []
