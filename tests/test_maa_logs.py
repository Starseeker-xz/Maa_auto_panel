from linux_maa.maa.logs import MaaCliLogTranslator, translate_maa_cli_log


def test_groups_completed_and_failed_tasks() -> None:
    translator = MaaCliLogTranslator()

    output = translator.translate(
        "[2026-06-26 18:45:26 INFO ] StartUp Start\n"
        "[2026-06-26 18:45:28 INFO ] StartUp Completed\n"
        "[2026-06-26 18:46:18 INFO ] Infrast Start\n"
        "[2026-06-26 18:46:19 WARN ] ProductUnknown\n"
        "[2026-06-26 18:47:20 ERROR] Infrast Error\n"
    )

    assert "18:45:26 已开始任务: StartUp" in output
    assert "18:45:28 任务 StartUp 成功" in output
    assert "18:46:18 已开始任务: Infrast" in output
    assert "18:46:19 产物识别失败\n" in output
    assert "18:47:20 任务 Infrast 失败" in output
    assert translator.task_results() == [
        {
            "type": "task",
            "name": "StartUp",
            "status": "succeeded",
            "rule_id": "maa-task-lifecycle",
            "panel_kind": "task",
            "started_at": "18:45:26",
            "ended_at": "18:45:28",
            "messages": [],
            "lines": [
                "[2026-06-26 18:45:26 INFO ] StartUp Start",
                "[2026-06-26 18:45:28 INFO ] StartUp Completed",
            ],
        },
        {
            "type": "task",
            "name": "Infrast",
            "status": "failed",
            "rule_id": "maa-task-lifecycle",
            "panel_kind": "task",
            "started_at": "18:46:18",
            "ended_at": "18:47:20",
            "messages": [
                {
                    "type": "text",
                    "text": "产物识别失败",
                    "tone": "warning",
                    "time": "18:46:19",
                },
            ],
            "lines": [
                "[2026-06-26 18:46:18 INFO ] Infrast Start",
                "[2026-06-26 18:46:19 WARN ] ProductUnknown",
                "[2026-06-26 18:47:20 ERROR] Infrast Error",
            ],
        },
    ]
    assert "raw" not in translator.entries()[1]["messages"][0]


def test_handles_split_log_chunks() -> None:
    translator = MaaCliLogTranslator()

    output = translator.translate("[2026-06-26 18:47:20 INFO ] Fight Sta")
    output += translator.translate("rt\n[2026-06-26 18:47:56 ERROR] Fight Error\n")

    assert "18:47:20 已开始任务: Fight" in output
    assert "18:47:56 任务 Fight 失败" in output
    assert translator.task_results()[0]["status"] == "failed"


def test_collapses_terminal_carriage_return_updates() -> None:
    translator = MaaCliLogTranslator(terminal_update_interval_seconds=999)

    output = translator.translate(
        "  3%|▎         | 64.0M/2.08G [00:17<08:59, 3.74MiB/s]\r"
        "  3%|▎         | 66.1M/2.08G [00:17<07:49, 4.29MiB/s]\r"
        "  4%|▍         | 84.9M/2.08G [00:22<06:59, 4.75MiB/s]\n",
        source="stderr",
    )
    entries = translator.entries()

    assert output.count("\n") == 2
    assert "64.0M/2.08G" in output
    assert "84.9M/2.08G" in output
    assert len(entries) == 1
    assert entries[0]["type"] == "line"
    assert entries[0]["text"] == "4%|▍         | 84.9M/2.08G [00:22<06:59, 4.75MiB/s]"
    assert entries[0]["tone"] == "info"


def test_carriage_return_newline_is_normal_log_line() -> None:
    translator = MaaCliLogTranslator()

    output = translator.translate("[2026-06-26 18:47:20 INFO ] Connected\r\n", source="stderr")

    assert output == "18:47:20 已连接\n"
    assert translator.entries()[0]["text"] == "已连接"


def test_flush_closes_running_task_as_unknown() -> None:
    translator = MaaCliLogTranslator()

    output = translator.translate("[2026-06-26 18:47:56 INFO ] Recruit Start\n")
    output += translator.flush()

    assert "18:47:56 任务 Recruit 未确认结束" in output
    assert translator.task_results()[0]["status"] == "unknown"


def test_compat_helper_flushes_one_shot_translation() -> None:
    output = translate_maa_cli_log("[2026-06-26 18:45:49 INFO ] Mall Start\n")

    assert "18:45:49 已开始任务: Mall" in output
    assert "18:45:49 任务 Mall 未确认结束" in output


def test_translates_screencap_method_and_cost() -> None:
    translator = MaaCliLogTranslator()

    output = translator.translate("[2026-06-30 18:18:44 INFO ] FastestWayToScreencap RawWithGzip 203\n")
    entry = translator.entries()[0]

    assert "18:18:44 已选择截图方式: RawWithGzip, 最短耗时 203 ms" in output
    assert entry["type"] == "line"
    assert entry["text"] == "已选择截图方式: RawWithGzip, 最短耗时 203 ms"
    assert "raw" not in entry
    assert entry["segments"] == [
        {"text": "已选择截图方式: "},
        {"text": "RawWithGzip", "tone": "info", "strong": True},
        {"text": ", 最短耗时 "},
        {"text": "203 ms", "tone": "success", "strong": True},
    ]


def test_adds_framework_preprocess_event() -> None:
    translator = MaaCliLogTranslator()

    output = translator.add_event("选择战斗关卡: 1-7", time="18:37:14", tone="info")
    entry = translator.entries()[0]

    assert output == "18:37:14 选择战斗关卡: 1-7\n"
    assert entry == {
        "type": "line",
        "text": "选择战斗关卡: 1-7",
        "tone": "info",
        "time": "18:37:14",
    }


def test_groups_summary_tail_into_one_entry() -> None:
    translator = MaaCliLogTranslator()

    output = translator.translate(
        "Summary\n"
        "----------------------------------------\n"
        "[启动 B 服] 2026-06-30 21:41:42 - 2026-06-30 21:42:25 (43s) Completed\n"
        "[公开招募] 2026-06-30 21:42:25 - 2026-06-30 21:42:40 (15s) Error\n"
        "Fight 1-7 1 times, drops:\n"
        "1. 固源岩 × 2\n"
        "total drops:\n"
        "Error: Some error occurred during running task!\n"
    )
    entry = translator.entries()[0]

    assert "运行摘要" in output
    assert entry["type"] == "summary"
    assert entry["status"] == "failed"
    assert len(entry["messages"]) == 6
    assert entry["messages"][0]["text"] == "启动 B 服: 完成, 用时 43s"
    assert entry["messages"][1]["tone"] == "danger"
    assert entry["messages"][2]["text"] == "作战 1-7 1 次，掉落："
    assert entry["messages"][4]["text"] == "合计掉落："
    assert entry["messages"][5]["text"] == "存在失败任务，maa-cli 返回错误。"


def test_keeps_summary_open_when_other_source_emits_timestamped_lines() -> None:
    translator = MaaCliLogTranslator()

    output = translator.translate("Summary\n", source="stdout")
    output += translator.translate("[2026-07-02 18:17:22 INFO ] AllTasksCompleted\n", source="stderr")
    output += translator.translate(
        "----------------------------------------\n"
        "[刷理智] 18:12:58 - 18:17:21 (4m 23s) Completed\n"
        "Fight 1-7 11 times, drops:\n",
        source="stdout",
    )
    entries = translator.entries()

    assert "运行摘要" in output
    assert entries[0]["type"] == "summary"
    assert entries[0]["messages"][0]["text"] == "刷理智: 完成, 用时 4m 23s"
    assert entries[0]["messages"][1]["text"] == "作战 1-7 11 次，掉落："
    assert entries[1]["text"] == "全部任务结束"


def test_groups_git_fetch_output_by_source() -> None:
    translator = MaaCliLogTranslator()

    output = translator.translate(
        "From https://github.com/MaaAssistantArknights/MaaResource\n"
        " * branch            main       -> FETCH_HEAD\n"
        "   8bcb4e1..a773275  main       -> origin/main\n"
        "[2026-07-02 18:01:13 INFO ] Connected\n",
        source="stderr",
    )
    entries = translator.entries()

    assert "资源拉取结果" in output
    assert entries[0]["type"] == "summary"
    assert entries[0]["title"] == "资源拉取结果"
    assert [message["text"] for message in entries[0]["messages"]] == [
        "From https://github.com/MaaAssistantArknights/MaaResource",
        " * branch            main       -> FETCH_HEAD",
        "   8bcb4e1..a773275  main       -> origin/main",
    ]
    assert entries[1]["text"] == "已连接"


def test_translates_recruit_fight_and_infrast_lines() -> None:
    translator = MaaCliLogTranslator()

    output = translator.translate(
        "[2026-07-02 18:06:30 INFO ] Recruit Start\n"
        "[2026-07-02 18:06:31 INFO ] RecruitResult: ★★★ 术师干员, 新手\n"
        "[2026-07-02 18:06:32 INFO ] RecruitTagsRefreshed: 2 times\n"
        "[2026-07-02 18:06:33 INFO ] RecruitTagsSelected: 新手\n"
        "[2026-07-02 18:06:34 INFO ] Recruit Completed\n"
        "[2026-07-02 18:06:36 INFO ] Infrast Start\n"
        "[2026-07-02 18:06:51 INFO ] EnterFacility Mfg #0\n"
        "[2026-07-02 18:07:04 INFO ] ProductOfFacility: PureGold\n"
        "[2026-07-02 18:07:05 INFO ] ProductChanged\n"
        "[2026-07-02 18:07:06 INFO ] CustomInfrastRoomOperators: 迷迭香, 槐琥\n"
        "[2026-07-02 18:07:07 INFO ] Infrast Completed\n"
        "[2026-07-02 18:12:58 INFO ] Fight Start\n"
        "[2026-07-02 18:13:19 INFO ] Current sanity: 70/210\n"
        "[2026-07-02 18:13:24 INFO ] Mission started (6 times, use 36 sanity)\n"
        "[2026-07-02 18:15:08 INFO ] Drops: furni × 1, 龙门币 × 432\n"
        "[2026-07-02 18:17:21 INFO ] Fight Completed\n",
        source="stderr",
    )
    results = translator.task_results()

    assert "公招识别结果: ★★★ 术师干员, 新手" in output
    assert "RecruitTagsRefreshed" not in output
    assert "选择公招标签: 新手" in output
    assert "进入设施: 制造站 #0" in output
    assert "设施产物: 赤金" in output
    assert "产物已切换" in output
    assert "换班干员: 迷迭香, 槐琥" in output
    assert "当前理智: 70/210" in output
    assert "开始行动 (6次，-36理智)" in output
    assert "掉落统计: 家具 × 1, 龙门币 × 432" in output
    assert [message["text"] for message in results[0]["messages"]] == [
        "公招识别结果: ★★★ 术师干员, 新手",
        "选择公招标签: 新手",
    ]


def test_translates_summary_recruit_and_infrast_details() -> None:
    translator = MaaCliLogTranslator()

    translator.translate(
        "Summary\n"
        "Detected tags:\n"
        "1. ★★★ 重装干员, Refreshed\n"
        "2. ★★★ 先锋干员, Recruited\n"
        "Recruited 1 times\n"
        "Refreshed 1 times\n"
        "Trade(SyntheticJade) with operators: 贝洛内, 伺夜, 空弦\n"
        "Power with operators: 格雷伊\n"
        "total drops: furni × 1, 龙门币 × 432\n"
    )
    messages = translator.entries()[0]["messages"]

    assert [message["text"] for message in messages] == [
        "识别到的公招标签：",
        "1. ★★★ 重装干员, 已刷新",
        "2. ★★★ 先锋干员, 已招募",
        "已招募 1 次",
        "已刷新 1 次",
        "贸易站（合成玉）: 贝洛内, 伺夜, 空弦",
        "发电站: 格雷伊",
        "合计掉落: 家具 × 1, 龙门币 × 432",
    ]


def test_labels_duplicate_task_types_from_expected_sequence() -> None:
    translator = MaaCliLogTranslator()
    translator.begin_task_sequence(
        [
            {"task_id": "fight-a", "source_name": "Fight", "name": "剿灭"},
            {"task_id": "fight-b", "source_name": "Fight", "name": "刷理智"},
        ]
    )

    output = translator.translate(
        "[2026-06-30 21:57:03 INFO ] Fight Start\n"
        "[2026-06-30 21:58:00 INFO ] Fight Completed\n"
        "[2026-06-30 21:58:00 INFO ] Fight Start\n"
        "[2026-06-30 22:00:32 INFO ] Fight Completed\n"
    )
    results = translator.task_results()

    assert "已开始任务: 剿灭" in output
    assert "已开始任务: 刷理智" in output
    assert [(item["task_id"], item["name"], item["source_name"], item["status"]) for item in results] == [
        ("fight-a", "剿灭", "Fight", "succeeded"),
        ("fight-b", "刷理智", "Fight", "succeeded"),
    ]


def test_translator_keeps_bounded_structured_tail() -> None:
    translator = MaaCliLogTranslator(max_log_entries=2, max_task_records=1, max_record_messages=1, max_record_lines=2)

    translator.translate(
        "[2026-06-30 21:57:03 INFO ] StartUp Start\n"
        "[2026-06-30 21:57:04 INFO ] Some first line\n"
        "[2026-06-30 21:57:05 INFO ] Some second line\n"
        "[2026-06-30 21:57:06 INFO ] Some third line\n"
        "[2026-06-30 21:57:07 INFO ] StartUp Completed\n"
        "[2026-06-30 21:57:08 INFO ] Mall Start\n"
        "[2026-06-30 21:57:09 INFO ] Mall Completed\n"
    )

    assert len(translator.entries()) == 2
    assert len(translator.task_results()) == 1
    assert translator.task_results()[0]["name"] == "Mall"
