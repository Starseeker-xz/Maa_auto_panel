from __future__ import annotations

import re
from dataclasses import dataclass, field

from linux_maa.maa.logs.records import LogTone, MaaLogMessage


TIME_VALUE_RE = r"(?:\d{4}-\d{2}-\d{2}\s+)?\d{2}:\d{2}:\d{2}"
SUMMARY_TASK_RE = re.compile(
    r"^\[(?P<task>.+?)\]\s+"
    rf"(?P<started>{TIME_VALUE_RE})\s+-\s+"
    rf"(?P<ended>{TIME_VALUE_RE})\s+"
    r"\((?P<elapsed>[^)]*)\)\s+"
    r"(?P<status>Completed|Error|Stopped|Unknown)\s*$"
)
SUMMARY_FIGHT_DROPS_RE = re.compile(r"^Fight\s+(?P<stage>\S+)\s+(?P<times>\d+)\s+times,\s+drops:\s*$")
MISSION_STARTED_RE = re.compile(r"^Mission started \((?P<times>\d+) times, use (?P<sanity>\d+) sanity\)$")
RECRUIT_TAGS_REFRESHED_RE = re.compile(r"^RecruitTagsRefreshed:\s+\d+\s+times$")
SUMMARY_COUNT_RE = re.compile(r"^(?P<kind>Recruited|Refreshed)\s+(?P<count>\d+)\s+times$")
ENTER_FACILITY_RE = re.compile(r"^EnterFacility\s+(?P<facility>[A-Za-z]+)(?:\s+(?P<index>#\d+))?$")
INFRABASE_SUMMARY_RE = re.compile(r"^(?P<facility>[A-Za-z]+)(?:\((?P<product>[^)]+)\))?\s+with operators:\s+(?P<operators>.*)$")

PRODUCT_LABELS = {
    "PureGold": "赤金",
    "SyntheticJade": "合成玉",
    "SkillLevel": "技能专精",
    "Money": "龙门币",
    "MoodAddition": "心情增益",
    "Drone": "无人机",
    "General": "线索收集",
    "HR": "公招刷新",
    "OriginStone": "源石碎片",
}

FACILITY_LABELS = {
    "Mfg": "制造站",
    "Trade": "贸易站",
    "Power": "发电站",
    "Control": "控制中枢",
    "Reception": "会客室",
    "Office": "办公室",
    "Dorm": "宿舍",
    "Training": "训练室",
}

COMMON_TERM_LABELS = {
    "furni": "家具",
    "Refreshed": "已刷新",
    "Recruited": "已招募",
}


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


def translate_task_line(body: str) -> str | None:
    translations = {
        "GameOffline": "游戏掉线",
        "ProductUnknown": "产物识别失败",
        "ProductIncorrect": "产物不匹配",
        "ProductChanged": "产物已切换",
        "NotEnoughStaff": "干员不足",
        "MissionStart": "作战开始",
        "MissionCompleted": "作战完成",
        "MissionFailed": "作战失败",
        "Refresh Tags": "刷新公招标签",
        "Recruit": "确认招募",
        "InfrastDormDoubleConfirmed": "宿舍换班二次确认",
    }

    mission_match = MISSION_STARTED_RE.match(body)
    if mission_match is not None:
        return f"开始行动 ({mission_match.group('times')}次，-{mission_match.group('sanity')}理智)"

    if body.startswith("Current sanity: "):
        return body.replace("Current sanity", "当前理智", 1)

    if body.startswith("Drops: "):
        return replace_common_terms(body.replace("Drops", "掉落统计", 1))

    if RECRUIT_TAGS_REFRESHED_RE.match(body):
        return None

    if body.startswith("RecruitResult: "):
        return body.replace("RecruitResult", "公招识别结果", 1)
    if body.startswith("RecruitResult "):
        return body.replace("RecruitResult", "公招识别结果", 1)

    if body.startswith("RecruitTagsSelected: "):
        return body.replace("RecruitTagsSelected", "选择公招标签", 1)

    facility_match = ENTER_FACILITY_RE.match(body)
    if facility_match is not None:
        facility = facility_label(facility_match.group("facility"))
        index = facility_match.group("index")
        return f"进入设施: {facility}{f' {index}' if index else ''}"

    if body.startswith("ProductOfFacility: "):
        product = body.split(": ", 1)[1]
        return f"设施产物: {product_label(product)}"

    if body.startswith("CustomInfrastRoomOperators: "):
        return body.replace("CustomInfrastRoomOperators", "换班干员", 1)

    return replace_common_terms(translations.get(body, body))


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

    if body == "Detected tags:":
        return MaaLogMessage(text="识别到的公招标签：", tone="info", raw=body)
    if body == "total drops:":
        return MaaLogMessage(text="合计掉落：", tone="info", raw=body)
    if body.startswith("total drops: "):
        return MaaLogMessage(text=replace_common_terms(body.replace("total drops", "合计掉落", 1)), tone="info", raw=body)

    count_match = SUMMARY_COUNT_RE.match(body)
    if count_match is not None:
        label = "已招募" if count_match.group("kind") == "Recruited" else "已刷新"
        return MaaLogMessage(text=f"{label} {count_match.group('count')} 次", tone="info", raw=body)

    infrast_line = translate_infrast_summary_line(body)
    if infrast_line != body:
        return MaaLogMessage(text=infrast_line, tone="info", raw=body)

    if body.startswith("Error:"):
        return MaaLogMessage(text="存在失败任务，maa-cli 返回错误。", tone="danger", raw=body)
    if body.startswith("Warning:"):
        return MaaLogMessage(text=body.replace("Warning:", "警告:", 1), tone="warning", raw=body)
    return MaaLogMessage(text=replace_common_terms(body), tone="default")


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


def replace_common_terms(text: str) -> str:
    output = text
    for source, target in COMMON_TERM_LABELS.items():
        output = output.replace(source, target)
    return output


def product_label(value: str) -> str:
    return PRODUCT_LABELS.get(value, value)


def facility_label(value: str) -> str:
    return FACILITY_LABELS.get(value, value)


def translate_infrast_summary_line(body: str) -> str:
    match = INFRABASE_SUMMARY_RE.match(body)
    if match is None:
        return body
    facility = facility_label(match.group("facility"))
    product = match.group("product")
    operators = match.group("operators")
    if product:
        return f"{facility}（{product_label(product)}）: {operators}"
    return f"{facility}: {operators}"
