from __future__ import annotations

from linux_maa.logs import LogSourceSpec, PlainLogTemplate, RunLogBuffer
from linux_maa.logs.pipeline import default_tone_for_source
from linux_maa.maa.log_templates import MaaLogTemplate


def maa_log(**kwargs: object) -> RunLogBuffer:
    log = RunLogBuffer(**kwargs)
    template = MaaLogTemplate()
    for source in ("maa-cli:stdout", "maa-cli:stderr"):
        log.register_source(LogSourceSpec(source, template, default_tone_for_source(source)))
    return log


def test_groups_completed_and_failed_tasks_as_blocks() -> None:
    log = maa_log()

    assert log.append(
        "[2026-06-26 18:45:26 INFO ] StartUp Start\n"
        "[2026-06-26 18:45:28 INFO ] StartUp Completed\n"
        "[2026-06-26 18:46:18 INFO ] Infrast Start\n"
        "[2026-06-26 18:46:19 WARN ] ProductUnknown\n"
        "[2026-06-26 18:47:20 ERROR] Infrast Error\n",
        source="maa-cli:stderr",
    )

    entries = log.entries()
    assert [entry["kind"] for entry in entries] == ["task", "task"]
    assert entries[0]["type"] == "block"
    assert entries[0]["name"] == "StartUp"
    assert entries[0]["status"] == "succeeded"
    assert entries[1]["name"] == "Infrast"
    assert entries[1]["status"] == "failed"
    assert entries[1]["messages"][0]["text"] == "产物识别失败"
    assert "raw" not in entries[1]["messages"][0]
    assert [result["status"] for result in log.task_results()] == ["succeeded", "failed"]


def test_handles_split_log_chunks() -> None:
    log = maa_log()

    output = ""
    output += log.pipeline.append("[2026-06-26 18:47:20 INFO ] Fight Sta", source="maa-cli:stderr")
    output += log.pipeline.append("rt\n[2026-06-26 18:47:56 ERROR] Fight Error\n", source="maa-cli:stderr")

    assert "18:47:20 已开始任务: Fight" in output
    assert "18:47:56 任务 Fight 失败" in output
    assert log.task_results()[0]["status"] == "failed"


def test_collapses_terminal_carriage_return_updates() -> None:
    log = maa_log()
    log.pipeline.terminal_update_interval_seconds = 999

    output = log.pipeline.append(
        "  3%|▎         | 64.0M/2.08G [00:17<08:59, 3.74MiB/s]\r"
        "  3%|▎         | 66.1M/2.08G [00:17<07:49, 4.29MiB/s]\r"
        "  4%|▍         | 84.9M/2.08G [00:22<06:59, 4.75MiB/s]\n",
        source="maa-cli:stderr",
    )
    entries = log.entries()

    assert output.count("\n") == 2
    assert "64.0M/2.08G" in output
    assert "84.9M/2.08G" in output
    assert len(entries) == 1
    assert entries[0]["kind"] == "line"
    assert entries[0]["messages"][0]["text"] == "4%|▍         | 84.9M/2.08G [00:22<06:59, 4.75MiB/s]"


def test_plain_source_does_not_trigger_maa_task_grouping() -> None:
    log = RunLogBuffer()
    template = PlainLogTemplate()
    log.register_source(LogSourceSpec("script:stderr", template, "warning"))

    output = log.pipeline.append("Summary\nFight Start\nplain stderr\n", source="script:stderr")
    entries = log.entries()

    assert output == "Summary\nFight Start\nplain stderr\n"
    assert [entry["kind"] for entry in entries] == ["line", "line", "line"]
    assert [entry["messages"][0]["text"] for entry in entries] == ["Summary", "Fight Start", "plain stderr"]
    assert all(entry["tone"] == "warning" for entry in entries)
    assert log.task_results() == []


def test_carriage_return_newline_is_normal_log_line() -> None:
    log = maa_log()

    output = log.pipeline.append("[2026-06-26 18:47:20 INFO ] Connected\r\n", source="maa-cli:stderr")

    assert output == "18:47:20 已连接\n"
    assert log.entries()[0]["messages"][0]["text"] == "已连接"


def test_flush_closes_running_block_as_unknown() -> None:
    log = maa_log()

    output = log.pipeline.append("[2026-06-26 18:47:56 INFO ] Recruit Start\n", source="maa-cli:stderr")
    output += log.pipeline.flush()

    assert "18:47:56 任务 Recruit 未确认结束" in output
    assert log.task_results()[0]["status"] == "unknown"


def test_translates_screencap_method_and_cost() -> None:
    log = maa_log()

    output = log.pipeline.append("[2026-06-30 18:18:44 INFO ] FastestWayToScreencap RawWithGzip 203\n", source="maa-cli:stderr")
    entry = log.entries()[0]

    assert "18:18:44 已选择截图方式: RawWithGzip, 最短耗时 203 ms" in output
    assert entry["type"] == "block"
    assert entry["kind"] == "line"
    assert entry["messages"][0]["text"] == "已选择截图方式: RawWithGzip, 最短耗时 203 ms"
    assert "raw" not in entry["messages"][0]
    assert entry["messages"][0]["segments"] == [
        {"text": "已选择截图方式: "},
        {"text": "RawWithGzip", "tone": "info", "strong": True},
        {"text": ", 最短耗时 "},
        {"text": "203 ms", "tone": "success", "strong": True},
    ]


def test_adds_framework_event_as_block() -> None:
    log = maa_log()

    output = log.pipeline.append_event("选择战斗关卡: 1-7", time="18:37:14", tone="info")
    entry = log.entries()[0]

    assert output == "18:37:14 选择战斗关卡: 1-7\n"
    assert entry["type"] == "block"
    assert entry["kind"] == "event"
    assert entry["messages"][0]["text"] == "选择战斗关卡: 1-7"
    assert entry["messages"][0]["time"] == "18:37:14"


def test_groups_summary_tail_into_one_block() -> None:
    log = maa_log()

    log.pipeline.append(
        "Summary\n"
        "----------------------------------------\n"
        "[启动 B 服] 2026-06-30 21:41:42 - 2026-06-30 21:42:25 (43s) Completed\n"
        "[公开招募] 2026-06-30 21:42:25 - 2026-06-30 21:42:40 (15s) Error\n"
        "Fight 1-7 1 times, drops:\n"
        "1. 固源岩 × 2\n"
        "total drops:\n"
        "Error: Some error occurred during running task!\n",
        source="maa-cli:stdout",
    )
    entry = log.entries()[0]

    assert entry["kind"] == "summary"
    assert entry["status"] == "failed"
    assert len(entry["messages"]) == 6
    assert entry["messages"][0]["text"] == "启动 B 服: 完成, 用时 43s"
    assert entry["messages"][1]["tone"] == "danger"
    assert entry["messages"][5]["text"] == "存在失败任务，maa-cli 返回错误。"


def test_keeps_summary_open_when_other_source_emits_timestamped_lines() -> None:
    log = maa_log()

    output = ""
    output += log.pipeline.append("Summary\n", source="maa-cli:stdout")
    output += log.pipeline.append("[2026-07-02 18:17:22 INFO ] AllTasksCompleted\n", source="maa-cli:stderr")
    output += log.pipeline.append(
        "----------------------------------------\n"
        "[刷理智] 18:12:58 - 18:17:21 (4m 23s) Completed\n"
        "Fight 1-7 11 times, drops:\n",
        source="maa-cli:stdout",
    )
    entries = log.entries()

    assert "运行摘要" in output
    assert entries[0]["kind"] == "summary"
    assert entries[0]["messages"][0]["text"] == "刷理智: 完成, 用时 4m 23s"
    assert entries[1]["messages"][0]["text"] == "全部任务结束"


def test_groups_stderr_git_fetch_diagnostics_by_source() -> None:
    log = maa_log()

    output = log.pipeline.append(
        "From https://github.com/MaaAssistantArknights/MaaResource\n"
        " * branch            main       -> FETCH_HEAD\n"
        "   8bcb4e1..a773275  main       -> origin/main\n"
        "[2026-07-02 18:01:13 INFO ] Connected\n",
        source="maa-cli:stderr",
    )
    entries = log.entries()

    assert "资源拉取诊断" in output
    assert entries[0]["kind"] == "summary"
    assert entries[0]["title"] == "资源拉取诊断"
    assert [message["text"] for message in entries[0]["messages"]] == [
        "From https://github.com/MaaAssistantArknights/MaaResource",
        " * branch            main       -> FETCH_HEAD",
        "   8bcb4e1..a773275  main       -> origin/main",
    ]
    assert entries[1]["messages"][0]["text"] == "已连接"


def test_summary_after_git_up_to_date_starts_run_summary_block() -> None:
    log = maa_log()

    log.pipeline.append(
        "Already up to date.\n"
        "Summary\n"
        "----------------------------------------\n"
        "[启动 B 服] 01:24:01 - 01:24:15 (14s) Completed\n",
        source="maa-cli:stdout",
    )
    entries = log.entries()

    assert [(entry["kind"], entry["title"]) for entry in entries] == [
        ("summary", "资源拉取结果"),
        ("summary", "运行摘要"),
    ]
    assert entries[0]["messages"][0]["text"] == "Already up to date."
    assert entries[1]["messages"][0]["text"] == "启动 B 服: 完成, 用时 14s"


def test_from_github_is_not_stdout_resource_update_start() -> None:
    log = maa_log()

    log.pipeline.append(
        "From https://github.com/MaaAssistantArknights/MaaResource\n"
        "Summary\n"
        "[启动 B 服] 01:24:01 - 01:24:15 (14s) Completed\n",
        source="maa-cli:stdout",
    )
    entries = log.entries()

    assert [(entry["kind"], entry.get("title", "")) for entry in entries] == [
        ("line", ""),
        ("summary", "运行摘要"),
    ]
    assert entries[0]["messages"][0]["text"] == "From https://github.com/MaaAssistantArknights/MaaResource"


def test_git_fast_forward_output_is_one_resource_update_block() -> None:
    log = maa_log()

    log.pipeline.append(
        "Updating 8bcb4e1..a773275\n"
        "Fast-forward\n"
        " resource/global/YoStarJP/resource/version.json | 6 +++---\n"
        " resource/global/YoStarKR/resource/version.json | 6 +++---\n"
        " 2 files changed, 6 insertions(+), 6 deletions(-)\n"
        "Summary\n"
        "[启动 B 服] 01:24:01 - 01:24:15 (14s) Completed\n",
        source="maa-cli:stdout",
    )
    entries = log.entries()

    assert [(entry["kind"], entry["title"]) for entry in entries] == [
        ("summary", "资源拉取结果"),
        ("summary", "运行摘要"),
    ]
    assert [message["text"] for message in entries[0]["messages"]] == [
        "Updating 8bcb4e1..a773275",
        "Fast-forward",
        " resource/global/YoStarJP/resource/version.json | 6 +++---",
        " resource/global/YoStarKR/resource/version.json | 6 +++---",
        " 2 files changed, 6 insertions(+), 6 deletions(-)",
    ]


def test_labels_duplicate_task_types_from_expected_sequence_and_reports_block_elapsed() -> None:
    log = maa_log()
    log.begin_task_sequence(
        [
            {"task_id": "fight-a", "source_name": "Fight", "name": "剿灭"},
            {"task_id": "fight-b", "source_name": "Fight", "name": "刷理智"},
        ]
    )

    log.pipeline.append("[2026-06-30 21:57:03 INFO ] Fight Start\n", source="maa-cli:stderr")
    current = log.current_block_elapsed_seconds(kind="task")
    assert current is not None
    assert current[0] == "剿灭"

    log.pipeline.append(
        "[2026-06-30 21:58:00 INFO ] Fight Completed\n"
        "[2026-06-30 21:58:00 INFO ] Fight Start\n"
        "[2026-06-30 22:00:32 INFO ] Fight Completed\n",
        source="maa-cli:stderr",
    )
    results = log.task_results()

    assert [(item["task_id"], item["name"], item["source_name"], item["status"]) for item in results] == [
        ("fight-a", "剿灭", "Fight", "succeeded"),
        ("fight-b", "刷理智", "Fight", "succeeded"),
    ]


def test_buffer_keeps_bounded_structured_tail() -> None:
    log = maa_log(max_task_records=1)
    log.pipeline.max_log_entries = 2
    log.pipeline.max_record_messages = 1
    log.pipeline.max_record_lines = 2

    log.pipeline.append(
        "[2026-06-30 21:57:03 INFO ] StartUp Start\n"
        "[2026-06-30 21:57:04 INFO ] Some first line\n"
        "[2026-06-30 21:57:05 INFO ] Some second line\n"
        "[2026-06-30 21:57:06 INFO ] Some third line\n"
        "[2026-06-30 21:57:07 INFO ] StartUp Completed\n"
        "[2026-06-30 21:57:08 INFO ] Mall Start\n"
        "[2026-06-30 21:57:09 INFO ] Mall Completed\n",
        source="maa-cli:stderr",
    )

    assert len(log.entries()) == 2
    assert len(log.task_results()) == 1
    assert log.task_results()[0]["name"] == "Mall"
