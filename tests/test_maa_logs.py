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
