from __future__ import annotations

import re
from dataclasses import dataclass, field

from linux_maa.maa.logs.records import LogTone, MaaLogMessage


SUMMARY_TASK_RE = re.compile(
    r"^\[(?P<task>.+?)\]\s+"
    r"(?P<started>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+-\s+"
    r"(?P<ended>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"\((?P<elapsed>[^)]*)\)\s+"
    r"(?P<status>Completed|Error|Stopped|Unknown)\s*$"
)
SUMMARY_FIGHT_DROPS_RE = re.compile(r"^Fight\s+(?P<stage>\S+)\s+(?P<times>\d+)\s+times,\s+drops:\s*$")


@dataclass(frozen=True)
class TranslatedMessage:
    text: str
    translated: bool = False
    tone: LogTone | None = None
    segments: list[dict[str, object]] = field(default_factory=list)


def translate_global_message(body: str) -> TranslatedMessage:
    translations = {
        "Connected": "已连接",
        "AllTasksCompleted": "全部任务结束",
        "Updating hot update files...": "检查热更新资源...",
        "Hot update completed successfully": "热更新资源检查完成",
    }
    if body in translations:
        return TranslatedMessage(translations[body], translated=True)
    if body.startswith("FastestWayToScreencap "):
        parts = body.split()
        if len(parts) >= 3:
            method = parts[1]
            cost_ms = parts[2]
            return TranslatedMessage(
                f"已选择截图方式: {method}, 最短耗时 {cost_ms} ms",
                translated=True,
                segments=[
                    {"text": "已选择截图方式: "},
                    {"text": method, "tone": "info", "strong": True},
                    {"text": ", 最短耗时 "},
                    {"text": f"{cost_ms} ms", "tone": "success", "strong": True},
                ],
            )
    return TranslatedMessage(body)


def translate_task_line(body: str) -> str:
    translations = {
        "GameOffline": "游戏掉线",
        "ProductUnknown": "产物识别失败",
        "ProductIncorrect": "产物不匹配",
        "NotEnoughStaff": "干员不足",
        "MissionStart": "作战开始",
        "MissionCompleted": "作战完成",
        "MissionFailed": "作战失败",
        "Refresh Tags": "刷新标签",
        "Recruit": "确认招募",
    }
    if body.startswith("EnterFacility "):
        return body.replace("EnterFacility", "进入设施", 1)
    if body.startswith("ProductOfFacility: "):
        return body.replace("ProductOfFacility", "设施产物", 1)
    if body.startswith("CustomInfrastRoomOperators: "):
        return body.replace("CustomInfrastRoomOperators", "自定义排班干员", 1)
    if body.startswith("RecruitResult "):
        return body.replace("RecruitResult", "招募结果", 1)
    return translations.get(body, body)


def translate_summary_message(body: str) -> MaaLogMessage | None:
    if not body or body == "----------------------------------------":
        return None

    task_match = SUMMARY_TASK_RE.match(body)
    if task_match is not None:
        task_name = task_match.group("task")
        elapsed = task_match.group("elapsed")
        status = task_match.group("status")
        status_label, tone = summary_status(status)
        text = f"{task_name}: {status_label}, 用时 {elapsed}"
        return MaaLogMessage(
            text=text,
            tone=tone,
            raw=body,
            segments=[
                {"text": task_name, "strong": True},
                {"text": ": "},
                {"text": status_label, "tone": tone, "strong": True},
                {"text": f", 用时 {elapsed}"},
            ],
        )

    fight_match = SUMMARY_FIGHT_DROPS_RE.match(body)
    if fight_match is not None:
        stage = fight_match.group("stage")
        times = fight_match.group("times")
        return MaaLogMessage(
            text=f"作战 {stage} {times} 次，掉落：",
            tone="info",
            raw=body,
            segments=[
                {"text": "作战 "},
                {"text": stage, "tone": "info", "strong": True},
                {"text": f" {times} 次，掉落："},
            ],
        )

    if body == "total drops:":
        return MaaLogMessage(text="合计掉落：", tone="info", raw=body)
    if body.startswith("Error:"):
        return MaaLogMessage(text="存在失败任务，maa-cli 返回错误。", tone="danger", raw=body)
    if body.startswith("Warning:"):
        return MaaLogMessage(text=body.replace("Warning:", "警告:", 1), tone="warning", raw=body)
    return MaaLogMessage(text=body, tone="default")


def summary_status(status: str) -> tuple[str, LogTone]:
    if status == "Completed":
        return "完成", "success"
    if status == "Error":
        return "失败", "danger"
    if status == "Stopped":
        return "已停止", "warning"
    return "未确认结束", "warning"


def is_global_line_translated(body: str) -> bool:
    return translate_global_message(body).translated


def is_task_line_translated(body: str) -> bool:
    return translate_task_line(body) != body
