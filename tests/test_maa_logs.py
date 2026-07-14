from __future__ import annotations

from maa_auto_panel.logs.pipeline import LogSourceSpec, plain_translate_line
from maa_auto_panel.logs.state import RunLogBuffer
from maa_auto_panel.maa.log_templates import begin_maa_task_sequence, configure_maa_log_template, maa_log_source_specs
from maa_auto_panel.maa.results import MaaTaskDescriptor, MaaTaskResultCollector, retry_result_summary
from maa_auto_panel.run_manager.logs import RunLogProfile


def maa_log(**kwargs: object) -> RunLogBuffer:
    log = RunLogBuffer(**kwargs)
    for source_spec in maa_log_source_specs():
        log.register_source(source_spec)
    configure_maa_log_template(log)
    return log


def test_task_result_collector_reads_raw_stderr_task_events() -> None:
    collector = MaaTaskResultCollector(
        [
            MaaTaskDescriptor(task_id="startup", source_name="StartUp", name="启动"),
            MaaTaskDescriptor(task_id="infrast", source_name="Infrast", name="基建"),
        ]
    )
    for line in [
        "[2026-06-26 18:45:26 INFO ] StartUp Start",
        "[2026-06-26 18:45:28 INFO ] StartUp Completed",
        "[2026-06-26 18:46:18 INFO ] Infrast Start",
        "[2026-06-26 18:46:19 WARN ] ProductUnknown",
        "[2026-06-26 18:47:20 ERROR] Infrast Error",
    ]:
        collector.consume_raw_line("maa-cli:stderr", line)
    collector.finish()

    assert [(item["task_id"], item["name"], item["source_name"], item["status"]) for item in collector.results] == [
        ("startup", "启动", "StartUp", "succeeded"),
        ("infrast", "基建", "Infrast", "failed"),
    ]
    assert collector.status_by_task_id(["startup", "infrast"]) == {"startup": "succeeded", "infrast": "failed"}


def test_retry_result_summary_lists_all_run_tasks_and_fades_unexecuted_tasks() -> None:
    tasks = [
        MaaTaskDescriptor(task_id="startup", source_name="StartUp", name="启动"),
        MaaTaskDescriptor(task_id="infrast", source_name="Infrast", name="基建"),
        MaaTaskDescriptor(task_id="fight", source_name="Fight", name="刷理智"),
        MaaTaskDescriptor(task_id="award", source_name="Award", name="领取奖励"),
        MaaTaskDescriptor(task_id="closedown", source_name="CloseDown", name="关闭游戏"),
    ]
    messages = retry_result_summary(
        tasks,
        [
            {"task_id": "startup", "status": "succeeded"},
            {"task_id": "infrast", "status": "failed"},
            {"task_id": "fight", "status": "stopped"},
            {"task_id": "award", "status": "unfinished"},
        ],
        planned_task_ids=["startup", "infrast", "fight", "award", "closedown"],
        retry_status="failed",
    )

    assert len(messages) == 1
    assert messages[0].text == "重试结果：✔️ 启动 · ❌ 基建 · ⚠️ 刷理智 · ⚠️ 领取奖励 · 关闭游戏"
    task_segments = messages[0].segments[1::2]
    assert task_segments == [
        {"text": "✔️ 启动", "tone": "success", "strong": True},
        {"text": "❌ 基建", "tone": "danger", "strong": True},
        {"text": "⚠️ 刷理智", "tone": "warning", "strong": True},
        {"text": "⚠️ 领取奖励", "tone": "warning", "strong": True},
        {"text": "关闭游戏"},
    ]
    assert [ord(character) for character in task_segments[0]["text"][:2]] == [0x2714, 0xFE0F]


def test_retry_result_summary_marks_planned_tasks_when_stopped_before_task_start() -> None:
    tasks = [
        MaaTaskDescriptor(task_id="startup", source_name="StartUp", name="启动"),
        MaaTaskDescriptor(task_id="fight", source_name="Fight", name="刷理智"),
    ]

    messages = retry_result_summary(
        tasks,
        [],
        planned_task_ids=["startup"],
        retry_status="stopped",
    )

    assert messages[0].text == "重试结果：⚠️ 启动 · 刷理智"
    assert messages[0].segments[1] == {"text": "⚠️ 启动", "tone": "warning", "strong": True}
    assert messages[0].segments[3] == {"text": "刷理智"}
    assert [ord(character) for character in messages[0].segments[1]["text"][:2]] == [0x26A0, 0xFE0F]


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
    assert entries[0]["closed"] is True
    assert entries[1]["name"] == "Infrast"
    assert entries[1]["status"] == "failed"
    assert entries[1]["messages"][0]["text"] == "产物识别失败"
    assert "raw" not in entries[1]["messages"][0]


def test_collapses_terminal_carriage_return_updates() -> None:
    log = maa_log()

    changed = log.pipeline.append(
        "  3%|▎         | 64.0M/2.08G [00:17<08:59, 3.74MiB/s]\r"
        "  3%|▎         | 66.1M/2.08G [00:17<07:49, 4.29MiB/s]\r"
        "  4%|▍         | 84.9M/2.08G [00:22<06:59, 4.75MiB/s]\n",
        source="maa-cli:stderr",
    )
    entries = log.entries()

    assert changed is True
    assert len(entries) == 1
    assert entries[0]["kind"] == "line"
    assert entries[0]["messages"][0]["text"] == "4%|▍         | 84.9M/2.08G [00:22<06:59, 4.75MiB/s]"


def test_plain_source_does_not_trigger_maa_task_grouping() -> None:
    log = RunLogBuffer()
    log.register_source(LogSourceSpec("script:stderr", "warning", plain_translate_line))

    log.pipeline.append("Summary\nFight Start\nplain stderr\n", source="script:stderr")
    entries = log.entries()

    assert [entry["kind"] for entry in entries] == ["line", "line", "line"]
    assert [entry["messages"][0]["text"] for entry in entries] == ["Summary", "Fight Start", "plain stderr"]
    assert all(entry["tone"] == "warning" for entry in entries)


def test_task_result_collector_marks_unfinished_on_finish_and_user_interrupt() -> None:
    collector = MaaTaskResultCollector([MaaTaskDescriptor(task_id="fight", source_name="Fight", name="刷理智")])
    collector.consume_raw_line("maa-cli:stderr", "[2026-06-26 18:47:20 INFO ] Fight Start")
    collector.finish()
    assert collector.results[0]["status"] == "unfinished"

    collector = MaaTaskResultCollector([MaaTaskDescriptor(task_id="fight", source_name="Fight", name="刷理智")])
    collector.consume_raw_line("maa-cli:stderr", "[2026-06-26 18:47:20 INFO ] Fight Start")
    collector.consume_raw_line("maa-cli:stderr", "[2026-06-26 18:47:56 ERROR] Error: Interrupted by user!")
    assert collector.results[0]["status"] == "unfinished"


def test_translates_screencap_method_and_cost() -> None:
    log = maa_log()

    log.pipeline.append("[2026-06-30 18:18:44 INFO ] FastestWayToScreencap RawWithGzip 203\n", source="maa-cli:stderr")
    entry = log.entries()[0]

    assert entry["type"] == "block"
    assert entry["kind"] == "line"
    assert str(entry["time"]).startswith("2026-06-30T18:18:44")
    assert "started_at" not in entry
    assert "ended_at" not in entry
    assert str(entry["opened_at"]).startswith("2026-06-30T18:18:44")
    assert str(entry["sealed_at"]).startswith("2026-06-30T18:18:44")
    assert entry["messages"][0]["text"] == "已选择截图方式: RawWithGzip, 最短耗时 203 ms"
    assert "raw" not in entry["messages"][0]
    assert entry["messages"][0]["segments"] == [
        {"text": "已选择截图方式: "},
        {"text": "RawWithGzip", "tone": "info", "strong": True},
        {"text": ", 最短耗时 "},
        {"text": "203 ms", "tone": "success", "strong": True},
    ]


def test_translates_fight_sanity_medicine_lines_with_observation_tones() -> None:
    log = maa_log()

    log.pipeline.append(
        "[2026-07-04 08:17:58 INFO ] Fight Start\n"
        "[2026-07-04 08:18:15 INFO ] Current sanity: 17/210\n"
        "[2026-07-04 08:18:22 INFO ] Use 1 expiring medicine\n"
        "[2026-07-04 08:18:29 INFO ] Mission started (6 times, use 36 sanity)\n",
        source="maa-cli:stderr",
    )
    messages = log.entries()[0]["messages"]

    assert [message["text"] for message in messages] == [
        "当前理智: 17/210",
        "使用 1 个临期理智药",
        "开始行动 (6次，-36理智)",
    ]
    assert [message["tone"] for message in messages] == ["theme", "warning", "theme"]
    assert "raw" not in messages[1]


def test_formats_fight_details_and_collapses_report_messages() -> None:
    log = maa_log()

    log.pipeline.append(
        "[2026-07-04 08:17:58 INFO ] Fight Start\n"
        "[2026-07-04 08:18:15 INFO ] Current sanity: 64/210\n"
        "[2026-07-04 08:18:29 INFO ] Mission started (5 times, use 30 sanity)\n"
        "[2026-07-04 08:20:29 INFO ] Drops: 固源岩 × 8\n"
        "[2026-07-04 08:20:30 INFO ] ReportToPenguinStats: https://penguin-stats.io/PenguinStats/api/v2/report\n"
        "[2026-07-04 08:20:31 INFO ] Successfully ReportToPenguinStats\n"
        "[2026-07-04 08:20:31 INFO ] ReportToYituliu: https://backend.yituliu.cn/maa/upload/stageDrop\n"
        "[2026-07-04 08:20:32 INFO ] Successfully ReportToYituliu\n",
        source="maa-cli:stderr",
    )
    messages = log.entries()[0]["messages"]

    assert [message["text"] for message in messages] == [
        "当前理智: 64/210",
        "开始行动 (5次，-30理智)",
        "掉落统计: 固源岩 × 8",
        "汇报成功",
    ]
    assert messages[0]["segments"] == [
        {"text": "当前理智: "},
        {"text": "64/210", "tone": "theme", "strong": True},
    ]
    assert messages[2]["indent"] == 1
    assert "segments" not in messages[2]
    assert messages[3]["indent"] == 1


def test_formats_infrast_and_recruit_actions() -> None:
    log = maa_log()

    log.pipeline.append(
        "[2026-07-04 08:17:58 INFO ] Infrast Start\n"
        "[2026-07-04 08:18:15 INFO ] EnterFacility Mfg #0\n"
        "[2026-07-04 08:18:16 INFO ] ProductOfFacility: PureGold\n"
        "[2026-07-04 08:18:17 INFO ] CustomInfrastRoomOperators: 迷迭香, 槐琥\n"
        "[2026-07-04 08:18:18 INFO ] Infrast Completed\n"
        "[2026-07-04 08:18:19 INFO ] Recruit Start\n"
        "[2026-07-04 08:18:20 INFO ] Refresh Tags\n"
        "[2026-07-04 08:18:21 INFO ] Recruit\n",
        source="maa-cli:stderr",
    )
    infrast, recruit = log.entries()

    assert infrast["messages"][0]["segments"] == [
        {"text": "进入设施: "},
        {"text": "制造站 #0", "tone": "theme", "strong": True},
    ]
    assert [message.get("indent", 0) for message in infrast["messages"]] == [0, 1, 1]
    assert [message["segments"][0]["strong"] for message in recruit["messages"]] == [True, True]


def test_adds_framework_event_as_block() -> None:
    log = maa_log()

    log.pipeline.append(
        "选择战斗关卡: 1-7\n",
        source="framework:event",
        metadata={"time": "18:37:14", "tone": "info", "event_key": "stage-selected"},
    )
    entry = log.entries()[0]

    assert entry["type"] == "block"
    assert entry["kind"] == "event"
    assert entry["messages"][0]["text"] == "选择战斗关卡: 1-7"
    assert entry["messages"][0]["time"] == "18:37:14"


def test_append_metadata_overrides_fallback_line_state() -> None:
    log = RunLogBuffer()

    log.pipeline.append(
        "raw framework text\n",
        source="framework:event",
        metadata={
            "time": "18:37:14",
            "tone": "warning",
            "kind_override": "event",
            "message_override": "展示文本",
            "status_override": "warning",
            "message_metadata": {"event_key": "demo"},
        },
    )
    entry = log.entries()[0]

    assert entry["kind"] == "event"
    assert entry["status"] == "warning"
    assert entry["messages"][0]["tone"] == "warning"
    assert entry["messages"][0]["metadata"] == {"event_key": "demo"}


def test_maa_line_metadata_accepts_warning_status() -> None:
    log = maa_log()

    log.pipeline.append(
        "[2026-07-04 08:17:58 INFO ] Connected\n",
        source="maa-cli:stderr",
        metadata={"status_override": "warning"},
    )
    entry = log.entries()[0]

    assert entry["status"] == "warning"


def test_groups_summary_tail_into_one_block() -> None:
    log = maa_log()

    log.pipeline.append(
        "Summary\n"
        "----------------------------------------\n"
        "[启动 B 服] 2026-06-30 21:41:42 - 2026-06-30 21:42:25 (43s) Completed\n"
        "[公开招募] 2026-06-30 21:42:25 - 2026-06-30 21:42:40 (15s) Error\n"
        "Fight 1-7 72 times, used 4 medicine (4 expiring), drops:\n"
        "1. 固源岩 × 2\n"
        "total drops: 固源岩 × 2\n"
        "Error: Some error occurred during running task!\n",
        source="maa-cli:stdout",
    )
    entry = log.entries()[0]

    assert entry["kind"] == "summary"
    assert entry["status"] == "failed"
    assert len(entry["messages"]) == 6
    assert entry["messages"][0]["text"] == "启动 B 服: 完成, 用时 43s"
    assert entry["messages"][0]["segments"][2] == {"text": "完成", "tone": "success"}
    assert entry["messages"][1]["tone"] == "danger"
    assert entry["messages"][1]["segments"][2] == {"text": "失败", "tone": "danger"}
    assert entry["messages"][2]["text"] == "作战 1-7 72 次，使用 4 个理智药（4 个临期），掉落："
    assert entry["messages"][2]["tone"] == "default"
    assert "segments" not in entry["messages"][2]
    assert entry["messages"][3]["segments"][0] == {"text": "1.", "tone": "theme", "strong": True}
    assert entry["messages"][4]["text"] == "合计掉落: 固源岩 × 2"
    assert entry["messages"][4]["tone"] == "theme"
    assert entry["messages"][5]["text"] == "Error: Some error occurred during running task!"
    assert entry["messages"][5]["raw"] == "Error: Some error occurred during running task!"
    assert [message.get("indent", 0) for message in entry["messages"]] == [0, 0, 1, 1, 1, 1]


def test_keeps_summary_open_when_other_source_emits_timestamped_lines() -> None:
    log = maa_log()

    log.pipeline.append("Summary\n", source="maa-cli:stdout")
    log.pipeline.append("[2026-07-02 18:17:22 INFO ] AllTasksCompleted\n", source="maa-cli:stderr")
    log.pipeline.append(
        "----------------------------------------\n"
        "[刷理智] 18:12:58 - 18:17:21 (4m 23s) Completed\n"
        "Fight 1-7 11 times, drops:\n",
        source="maa-cli:stdout",
    )
    entries = log.entries()

    assert entries[0]["kind"] == "summary"
    assert entries[0]["messages"][0]["text"] == "刷理智: 完成, 用时 4m 23s"
    assert entries[1]["messages"][0]["text"] == "全部任务结束"


def test_groups_stderr_git_fetch_diagnostics_by_source() -> None:
    log = maa_log()

    log.pipeline.append(
        "From https://github.com/MaaAssistantArknights/MaaResource\n"
        " * branch            main       -> FETCH_HEAD\n"
        "   8bcb4e1..a773275  main       -> origin/main\n"
        "[2026-07-02 18:01:13 INFO ] Connected\n",
        source="maa-cli:stderr",
    )
    entries = log.entries()

    assert entries[0]["kind"] == "output"
    assert entries[0]["title"] == "资源拉取诊断"
    assert [message["text"] for message in entries[0]["messages"]] == [
        "From https://github.com/MaaAssistantArknights/MaaResource",
        " * branch            main       -> FETCH_HEAD",
        "   8bcb4e1..a773275  main       -> origin/main",
    ]
    assert entries[1]["messages"][0]["text"] == "已连接"


def test_silences_multiline_operbox_and_depot_json_payloads() -> None:
    log = maa_log()

    log.pipeline.append(
        "[2026-07-14 03:00:00 INFO ] OperBox Start\n"
        "[2026-07-14 03:00:01 INFO ] OperBox: {\n"
        '[2026-07-14 03:00:01 INFO ]   "details": {\n'
        '    "done": true,\n'
        '    "own_opers": [{"id": "char_001", "name": "能天使", "note": "} inside string"}]\n'
        "  }\n"
        "}\n"
        "[2026-07-14 03:00:02 INFO ] OperBox Completed\n"
        "[2026-07-14 03:00:03 INFO ] Depot: {\"details\": {\"done\": true}}\n"
        "[2026-07-14 03:00:04 INFO ] Connected\n",
        source="maa-cli:stderr",
    )

    entries = log.entries()
    assert entries[0]["kind"] == "task"
    assert entries[0]["status"] == "succeeded"
    assert entries[0]["messages"] == []
    assert entries[1]["messages"][0]["text"] == "已连接"
    assert all("own_opers" not in line for entry in entries for line in entry["lines"])


def test_json_suppression_state_is_isolated_per_log_buffer() -> None:
    profile = RunLogProfile(source_specs=maa_log_source_specs(), configure_buffer=configure_maa_log_template)
    first = profile.new_buffer()
    second = profile.new_buffer()

    first.pipeline.append("[2026-07-14 03:00:00 INFO ] Depot: {\n", source="maa-cli:stderr")
    second.pipeline.append("[2026-07-14 03:00:01 INFO ] Connected\n", source="maa-cli:stderr")

    assert first.entries() == []
    assert second.entries()[0]["messages"][0]["text"] == "已连接"


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
        ("output", "资源拉取结果"),
        ("summary", "运行摘要"),
    ]
    assert entries[0]["messages"][0]["text"] == "Already up to date."
    assert entries[1]["messages"][0]["text"] == "启动 B 服: 完成, 用时 14s"


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
        ("output", "资源拉取结果"),
        ("summary", "运行摘要"),
    ]
    assert [message["text"] for message in entries[0]["messages"]] == [
        "Updating 8bcb4e1..a773275",
        "Fast-forward",
        " resource/global/YoStarJP/resource/version.json | 6 +++---",
        " resource/global/YoStarKR/resource/version.json | 6 +++---",
        " 2 files changed, 6 insertions(+), 6 deletions(-)",
    ]


def test_task_result_collector_labels_duplicate_task_types_from_expected_sequence() -> None:
    collector = MaaTaskResultCollector(
        [
            MaaTaskDescriptor(task_id="fight-a", source_name="Fight", name="剿灭"),
            MaaTaskDescriptor(task_id="fight-b", source_name="Fight", name="刷理智"),
        ]
    )
    for line in [
        "[2026-06-30 21:57:03 INFO ] Fight Start",
        "[2026-06-30 21:58:00 INFO ] Fight Completed",
        "[2026-06-30 21:58:00 INFO ] Fight Start",
        "[2026-06-30 22:00:32 INFO ] Fight Completed",
    ]:
        collector.consume_raw_line("maa-cli:stderr", line)
    collector.finish()

    assert [(item["task_id"], item["name"], item["source_name"], item["status"]) for item in collector.results] == [
        ("fight-a", "剿灭", "Fight", "succeeded"),
        ("fight-b", "刷理智", "Fight", "succeeded"),
    ]


def test_visible_task_blocks_use_expected_sequence_for_duplicate_task_types() -> None:
    log = maa_log()
    begin_maa_task_sequence(
        log,
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
    entries = log.entries()

    assert [(entry["task_id"], entry["name"], entry["source_name"], entry["status"]) for entry in entries] == [
        ("fight-a", "剿灭", "Fight", "succeeded"),
        ("fight-b", "刷理智", "Fight", "succeeded"),
    ]


def test_buffer_keeps_bounded_structured_tail() -> None:
    log = maa_log()
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
