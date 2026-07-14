from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from maa_auto_panel.logs.pipeline import (
    ActiveBlock,
    BlockDefinition,
    BlockStartContext,
    BlockStartOutcome,
    CloseReason,
    LogLineInput,
    LogLineTranslation,
    LogPipelineSession,
    LogSourceSpec,
    default_tone_for_source,
    format_time_prefix,
    plain_translate_line,
)
from maa_auto_panel.logs.records import BlockStatus, LogMessage, LogTone
from maa_auto_panel.time_utils import server_datetime_from_text

if TYPE_CHECKING:
    from maa_auto_panel.logs.state import RunLogBuffer


TIME_VALUE_RE = r"(?:\d{4}-\d{2}-\d{2}\s+)?\d{2}:\d{2}:\d{2}"
SUMMARY_TASK_RE = re.compile(
    r"^\[(?P<task>.+?)\]\s+"
    rf"(?P<started>{TIME_VALUE_RE})\s+-\s+"
    rf"(?P<ended>{TIME_VALUE_RE})\s+"
    r"\((?P<elapsed>[^)]*)\)\s+"
    r"(?P<status>Completed|Error|Stopped|Unknown)\s*$"
)
SUMMARY_FIGHT_DROPS_RE = re.compile(
    r"^Fight\s+(?P<stage>\S+)\s+(?P<times>\d+)\s+times"
    r"(?:,\s+used\s+(?P<medicine>\d+)\s+medicine(?:\s+\((?P<expiring>\d+)\s+expiring\))?)?,\s+drops:\s*$"
)
MISSION_STARTED_RE = re.compile(r"^Mission started \((?P<times>\d+) times, use (?P<sanity>\d+) sanity\)$")
CURRENT_SANITY_RE = re.compile(r"^Current sanity:\s+(?P<current>\d+)/(?P<total>\d+)$")
USE_MEDICINE_RE = re.compile(r"^Use\s+(?P<count>\d+)\s+(?P<expiring>expiring\s+)?medicine$")
SUMMARY_DROP_ITEM_RE = re.compile(r"^(?P<index>\d+)\.\s+(?P<drops>.+)$")
RECRUIT_TAGS_REFRESHED_RE = re.compile(r"^RecruitTagsRefreshed:\s+\d+\s+times$")
SUMMARY_COUNT_RE = re.compile(r"^(?P<kind>Recruited|Refreshed)\s+(?P<count>\d+)\s+times$")
ENTER_FACILITY_RE = re.compile(r"^EnterFacility\s+(?P<facility>[A-Za-z]+)(?:\s+(?P<index>#\d+))?$")
INFRABASE_SUMMARY_RE = re.compile(r"^(?P<facility>[A-Za-z]+)(?:\((?P<product>[^)]+)\))?\s+with operators:\s+(?P<operators>.*)$")
LOG_LINE_RE = re.compile(
    r"^\[(?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>[A-Z]+)\s*\]\s*(?P<body>.*)$"
)
TASK_EVENT_RE = re.compile(r"^(?P<task>[A-Za-z][A-Za-z0-9_]*?)\s+(?P<event>Start|Completed|Error|Stopped)\s*$")
GIT_UPDATE_RE = re.compile(r"^Updating [0-9a-f]{4,}\.\.[0-9a-f]{4,}$")

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

LEVEL_TONE: dict[str, LogTone] = {
    "ERROR": "danger",
    "WARN": "warning",
    "INFO": "info",
}


@dataclass(frozen=True)
class TranslatedMessage:
    """Result of translating a raw MAA log message: text, translated flag, optional tone."""

    text: str
    translated: bool = False
    tone: LogTone | None = None
    segments: list[dict[str, object]] = field(default_factory=list)


@dataclass
class MaaLogState:
    expected_tasks: list[dict[str, str]] = field(default_factory=list)
    expected_task_index: int = 0

    def begin_task_sequence(self, tasks: list[dict[str, str]]) -> None:
        self.expected_tasks = [
            {
                "task_id": str(task.get("task_id") or ""),
                "source_name": str(task.get("source_name") or task.get("type") or task.get("name") or ""),
                "name": str(task.get("name") or task.get("source_name") or task.get("type") or ""),
            }
            for task in tasks
            if task.get("source_name") or task.get("type") or task.get("name")
        ]
        self.expected_task_index = 0

    def next_expected_task(self, source_name: str) -> dict[str, str]:
        for index in range(self.expected_task_index, len(self.expected_tasks)):
            task = self.expected_tasks[index]
            if task.get("source_name") != source_name:
                continue
            self.expected_task_index = index + 1
            return task
        return {"task_id": "", "source_name": source_name, "name": source_name}


@dataclass(frozen=True)
class TaskEventMatch:
    task_name: str
    status: BlockStatus
    parsed: dict[str, str | None]
    interrupted: bool = False


def register_maa_log_sources(log: "RunLogBuffer") -> MaaLogState:
    state = MaaLogState()
    log.pipeline.register_task_sequence_handler(state.begin_task_sequence)
    for source in ("maa-cli:stdout", "maa-cli:stderr"):
        log.register_source(LogSourceSpec(source, default_tone_for_source(source), translate_maa_cli_line))
    for definition in maa_block_definitions(state):
        log.pipeline.register_block(definition)
    return state


def maa_block_definitions(state: MaaLogState) -> list[BlockDefinition]:
    return [
        BlockDefinition(
            kind="task",
            source_predicate=lambda source: source == "maa-cli:stderr",
            start_matcher=_match_task_event,
            end_matcher=_match_task_end,
            translate_line=_translate_task_body_line,
            on_start=lambda active, line, match, context: _on_task_start(state, active, line, match, context),
            on_close=_on_task_close,
            default_status="running",
            default_tone="info",
            rule_id="maa-task-lifecycle",
            panel_kind="task",
        ),
        BlockDefinition(
            kind="summary",
            source_predicate=lambda source: source == "maa-cli:stdout",
            start_matcher=_match_run_summary_start,
            passive_boundary_matcher=_match_timestamp_boundary,
            translate_line=_translate_summary_line,
            on_start=_on_summary_start,
            on_close=_on_inert_close,
            default_title="运行摘要",
            default_status="succeeded",
            default_tone="success",
            rule_id="maa-run-summary",
            panel_kind="summary",
        ),
        BlockDefinition(
            kind="output",
            source_predicate=lambda source: source == "maa-cli:stdout",
            start_matcher=_match_stdout_resource_update_start,
            passive_boundary_matcher=_match_stdout_resource_update_boundary,
            translate_line=_translate_resource_output_line,
            on_start=lambda active, line, match, context: _on_resource_output_start(active, line, context.session, title="资源拉取结果"),
            on_close=_on_inert_close,
            default_title="资源拉取结果",
            default_status="succeeded",
            default_tone="info",
            rule_id="maa-stdout-resource-update",
            panel_kind="summary",
        ),
        BlockDefinition(
            kind="output",
            source_predicate=lambda source: source.endswith(":stderr"),
            start_matcher=_match_stderr_fetch_start,
            passive_boundary_matcher=_match_timestamp_boundary,
            translate_line=_translate_resource_output_line,
            on_start=lambda active, line, match, context: _on_resource_output_start(active, line, context.session, title="资源拉取诊断"),
            on_close=_on_inert_close,
            default_title="资源拉取诊断",
            default_status="succeeded",
            default_tone="info",
            rule_id="maa-stderr-fetch-diagnostics",
            panel_kind="summary",
        ),
    ]


def translate_maa_cli_line(source: str, raw: str, metadata: dict[str, object], context: LogPipelineSession) -> LogLineTranslation | None:
    if "message_override" in metadata or "kind_override" in metadata:
        return plain_translate_line(source, raw, metadata, context)

    parsed = parse_log_line(raw)
    body = str(parsed["body"] or "")
    time_text = _metadata_str(metadata, "time") or parsed["time"]
    level = parsed["level"]
    default_tone = context.source_spec(source).default_tone
    tone = _metadata_tone(metadata, LEVEL_TONE.get(str(level), default_tone) if level is not None else default_tone)
    translated = translate_global_message(body)
    if not translated.translated:
        translated = translate_task_message(body)
    message = LogMessage(
        text=translated.text,
        time=time_text,
        tone=translated.tone or tone,
        raw=None if translated.translated else raw,
        segments=translated.segments,
        metadata=_metadata_dict(metadata, "message_metadata"),
    )
    return LogLineTranslation(
        text=message.text,
        kind=_metadata_str(metadata, "kind_override") or "line",
        title=_metadata_str(metadata, "title_override") or "",
        status=_metadata_status(metadata) or "default",
        time=time_text,
        tone=message.tone,
        messages=[message],
        lines=[raw],
        raw=None if translated.translated else raw,
        metadata=_metadata_dict(metadata, "entry_metadata"),
    )


def _match_task_event(line: LogLineInput, session: LogPipelineSession) -> TaskEventMatch | None:
    parsed = parse_log_line(line.raw)
    match = TASK_EVENT_RE.match(str(parsed["body"] or ""))
    if match is None:
        return None
    status = task_status(match.group("event"))
    if status is None:
        return None
    return TaskEventMatch(task_name=match.group("task"), status=status, parsed=parsed)


def _match_task_end(active: ActiveBlock, line: LogLineInput, session: LogPipelineSession) -> TaskEventMatch | None:
    parsed = parse_log_line(line.raw)
    body = str(parsed["body"] or "")
    current_name = active.entry.source_name or active.entry.name
    if body == "Error: Interrupted by user!":
        return TaskEventMatch(task_name=current_name or active.entry.title, status="unfinished", parsed=parsed, interrupted=True)

    match = TASK_EVENT_RE.match(body)
    if match is None:
        return None
    status = task_status(match.group("event"))
    if status is None or status == "running":
        return None
    task_name = match.group("task")
    if current_name != task_name:
        return None
    return TaskEventMatch(task_name=task_name, status=status, parsed=parsed)


def _on_task_start(
    state: MaaLogState,
    active: ActiveBlock,
    line: LogLineInput,
    match: object | None,
    context: BlockStartContext,
) -> BlockStartOutcome:
    if not isinstance(match, TaskEventMatch):
        return BlockStartOutcome()

    expected_task = state.next_expected_task(match.task_name)
    display_name = expected_task.get("name") or match.task_name
    entry = active.entry
    entry.title = f"任务 {display_name}"
    entry.status = match.status
    entry.tone = tone_for_status(match.status)
    entry.name = display_name
    entry.task_id = expected_task.get("task_id") or None
    entry.source_name = match.task_name
    entry.rule_id = "maa-task-lifecycle"
    entry.panel_kind = "task"
    entry.time = match.parsed["time"] or line.time

    if match.status == "running":
        entry.opened_at = match.parsed["time"] or line.time
        started = time.monotonic()
        entry.metadata["started_monotonic"] = started
        active.context["started_monotonic"] = started
        return BlockStartOutcome()

    entry.sealed_at = match.parsed["time"] or line.time
    return BlockStartOutcome(keep_active=False)


def _translate_task_body_line(active: ActiveBlock, line: LogLineInput, session: LogPipelineSession) -> str:
    parsed = parse_log_line(line.raw)
    body = str(parsed["body"] or "")
    time_text = parsed["time"] or line.time
    level = parsed["level"]
    default_tone = LEVEL_TONE.get(str(level), session.source_spec(line.source).default_tone) if level is not None else line.tone
    active.entry.lines.append(line.raw)
    report_message = _translate_report_message(active, body)
    if report_message is not None:
        translated_task_line = report_message
    else:
        active.context.pop("report_success_emitted", None)
        translated_task_line = translate_task_message(body)
    if not translated_task_line.text:
        return ""
    message = LogMessage(
        text=translated_task_line.text,
        time=time_text,
        tone=translated_task_line.tone or default_tone,
        raw=None if translated_task_line.translated else line.raw,
        segments=translated_task_line.segments,
        indent=(
            1
            if body.startswith(
                ("Drops: ", "ProductOfFacility: ", "CustomInfrastRoomOperators: ", "Successfully ReportTo")
            )
            else 0
        ),
    )
    active.entry.messages.append(message)
    return f"{format_time_prefix(message.time)}{message.text}\n"


def _on_task_close(
    active: ActiveBlock,
    reason: CloseReason,
    line: LogLineInput | None,
    match: object | None,
    session: LogPipelineSession,
) -> str:
    entry = active.entry
    status: BlockStatus = "unknown"
    time_text: str | None = None

    if reason == "matched_end" and isinstance(match, TaskEventMatch):
        status = match.status
        time_text = match.parsed["time"]
        if line is not None and match.interrupted:
            entry.messages.append(LogMessage(text="用户中断", time=time_text, tone="warning", raw=line.raw))
    elif entry.status and entry.status not in {"default", "running"}:
        status = entry.status
    elif entry.status == "running":
        status = "unfinished"

    entry.status = status
    entry.tone = tone_for_status(status)
    if time_text:
        entry.sealed_at = time_text
    entry.metadata.pop("started_monotonic", None)
    active.context.pop("started_monotonic", None)
    active.locked_fields.update({"status", "tone", "sealed_at"})
    return ""


def _match_run_summary_start(line: LogLineInput, session: LogPipelineSession) -> str | None:
    parsed = parse_log_line(line.raw)
    return "summary" if parsed["body"] == "Summary" else None


def _on_summary_start(active: ActiveBlock, line: LogLineInput, match: object | None, context: BlockStartContext) -> str:
    active.entry.title = "运行摘要"
    active.entry.status = "succeeded"
    active.entry.tone = "success"
    active.entry.lines.append(line.raw)
    return "运行摘要\n"


def _translate_summary_line(active: ActiveBlock, line: LogLineInput, session: LogPipelineSession) -> str:
    parsed = parse_log_line(line.raw)
    body = str(parsed["body"] or "")
    message = translate_summary_message(body)
    active.entry.lines.append(line.raw)
    if message is None:
        return ""
    if SUMMARY_TASK_RE.match(body) is None:
        message.indent = 1
    active.entry.messages.append(message)
    if message.tone == "danger":
        active.entry.status = "failed"
        active.entry.tone = "danger"
    elif message.tone == "warning" and active.entry.status != "failed":
        active.entry.status = "stopped"
        active.entry.tone = "warning"
    return f"{message.text}\n"


def _match_stdout_resource_update_start(line: LogLineInput, session: LogPipelineSession) -> str | None:
    return "resource-update" if is_stdout_resource_update_start(line.raw) else None


def _match_stderr_fetch_start(line: LogLineInput, session: LogPipelineSession) -> str | None:
    return "stderr-fetch" if is_stderr_fetch_start(line.raw, line.source) else None


def _on_resource_output_start(active: ActiveBlock, line: LogLineInput, session: LogPipelineSession, *, title: str) -> str:
    active.entry.title = title
    active.entry.status = "succeeded"
    active.entry.tone = "info"
    return f"{title}\n" + _translate_resource_output_line(active, line, session)


def _translate_resource_output_line(active: ActiveBlock, line: LogLineInput, session: LogPipelineSession) -> str:
    message = LogMessage(text=line.raw, tone="info", raw=line.raw)
    active.entry.messages.append(message)
    if not active.entry.lines or active.entry.lines[-1] != line.raw:
        active.entry.lines.append(line.raw)
    return f"{line.raw}\n"


def _match_timestamp_boundary(active: ActiveBlock, line: LogLineInput, session: LogPipelineSession) -> str | None:
    parsed = parse_log_line(line.raw)
    return "timestamped-line" if parsed["time"] is not None else None


def _match_stdout_resource_update_boundary(active: ActiveBlock, line: LogLineInput, session: LogPipelineSession) -> str | None:
    parsed = parse_log_line(line.raw)
    if parsed["body"] == "Summary":
        return "summary"
    if parsed["time"] is not None:
        return "timestamped-line"
    return None


def _on_inert_close(
    active: ActiveBlock,
    reason: CloseReason,
    line: LogLineInput | None,
    match: object | None,
    session: LogPipelineSession,
) -> str:
    return ""


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
    text = translate_task_message(body).text
    return text or None


def translate_task_message(body: str) -> TranslatedMessage:
    translations = {
        "GameOffline": "游戏掉线",
        "ProductUnknown": "产物识别失败",
        "ProductIncorrect": "产物不匹配",
        "ProductChanged": "产物已切换",
        "NotEnoughStaff": "干员不足",
        "MissionStart": "作战开始",
        "MissionCompleted": "作战完成",
        "MissionFailed": "作战失败",
        "InfrastDormDoubleConfirmed": "宿舍换班二次确认",
    }

    recruit_actions = {
        "Refresh Tags": "刷新公招标签",
        "Recruit": "确认招募",
    }
    if body in recruit_actions:
        action = recruit_actions[body]
        return TranslatedMessage(
            action,
            translated=True,
            segments=[{"text": action, "tone": "theme", "strong": True}],
        )

    mission_match = MISSION_STARTED_RE.match(body)
    if mission_match is not None:
        times = mission_match.group("times")
        sanity = mission_match.group("sanity")
        return TranslatedMessage(
            f"开始行动 ({times}次，-{sanity}理智)",
            translated=True,
            tone="theme",
            segments=[
                {"text": "开始行动", "tone": "theme", "strong": True},
                {"text": " ("},
                {"text": f"{times}"},
                {"text": "次，-"},
                {"text": f"{sanity}"},
                {"text": "理智)"},
            ],
        )

    sanity_match = CURRENT_SANITY_RE.match(body)
    if sanity_match is not None:
        current = sanity_match.group("current")
        total = sanity_match.group("total")
        return TranslatedMessage(
            f"当前理智: {current}/{total}",
            translated=True,
            tone="theme",
            segments=[
                {"text": "当前理智: "},
                {"text": f"{current}/{total}", "tone": "theme", "strong": True},
            ],
        )

    medicine_match = USE_MEDICINE_RE.match(body)
    if medicine_match is not None:
        count = medicine_match.group("count")
        expiring = bool(medicine_match.group("expiring"))
        label = "临期理智药" if expiring else "理智药"
        return TranslatedMessage(
            f"使用 {count} 个{label}",
            translated=True,
            tone="warning",
            segments=[
                {"text": "使用 ", "tone": "warning"},
                {"text": count, "tone": "warning", "strong": True},
                {"text": f" 个{label}", "tone": "warning", "strong": True},
            ],
        )

    if body.startswith("Drops: "):
        drops = replace_common_terms(body.removeprefix("Drops: "))
        return TranslatedMessage(
            f"掉落统计: {drops}",
            translated=True,
        )

    if RECRUIT_TAGS_REFRESHED_RE.match(body):
        return TranslatedMessage("", translated=True)

    if body.startswith("RecruitResult: "):
        return TranslatedMessage(body.replace("RecruitResult", "公招识别结果", 1), translated=True)
    if body.startswith("RecruitResult "):
        return TranslatedMessage(body.replace("RecruitResult", "公招识别结果", 1), translated=True)

    if body.startswith("RecruitTagsSelected: "):
        return TranslatedMessage(body.replace("RecruitTagsSelected", "选择公招标签", 1), translated=True)

    facility_match = ENTER_FACILITY_RE.match(body)
    if facility_match is not None:
        facility = facility_label(facility_match.group("facility"))
        index = facility_match.group("index")
        facility_name = f"{facility}{f' {index}' if index else ''}"
        return TranslatedMessage(
            f"进入设施: {facility_name}",
            translated=True,
            segments=[
                {"text": "进入设施: "},
                {"text": facility_name, "tone": "theme", "strong": True},
            ],
        )

    if body.startswith("ProductOfFacility: "):
        product = body.split(": ", 1)[1]
        return TranslatedMessage(f"设施产物: {product_label(product)}", translated=True)

    if body.startswith("CustomInfrastRoomOperators: "):
        return TranslatedMessage(body.replace("CustomInfrastRoomOperators", "换班干员", 1), translated=True)

    translated = replace_common_terms(translations.get(body, body))
    return TranslatedMessage(translated, translated=translated != body)


def translate_summary_message(body: str) -> LogMessage | None:
    if not body or body == "----------------------------------------":
        return None

    task_match = SUMMARY_TASK_RE.match(body)
    if task_match is not None:
        task_name = task_match.group("task")
        elapsed = task_match.group("elapsed")
        status = task_match.group("status")
        status_label, tone = summary_status(status)
        text = f"{task_name}: {status_label}, 用时 {elapsed}"
        return LogMessage(
            text=text,
            tone=tone,
            raw=body,
            segments=[
                {"text": task_name, "tone": tone, "strong": True},
                {"text": ": ", "tone": tone},
                {"text": status_label, "tone": tone},
                {"text": f", 用时 {elapsed}"},
            ],
        )

    fight_match = SUMMARY_FIGHT_DROPS_RE.match(body)
    if fight_match is not None:
        stage = fight_match.group("stage")
        times = fight_match.group("times")
        medicine = fight_match.group("medicine")
        expiring = fight_match.group("expiring")
        medicine_text = ""
        if medicine:
            if expiring:
                medicine_text = f"，使用 {medicine} 个理智药（{expiring} 个临期）"
            else:
                medicine_text = f"，使用 {medicine} 个理智药"
        return LogMessage(
            text=f"作战 {stage} {times} 次{medicine_text}，掉落：",
            raw=body,
        )

    drop_item_match = SUMMARY_DROP_ITEM_RE.match(body)
    if drop_item_match is not None:
        index = drop_item_match.group("index")
        drops = replace_common_terms(drop_item_match.group("drops"))
        return LogMessage(
            text=f"{index}. {drops}",
            tone="theme",
            raw=body,
            segments=[
                {"text": f"{index}.", "tone": "theme", "strong": True},
                {"text": f" {drops}"},
            ],
        )

    if body == "Detected tags:":
        return LogMessage(text="识别到的公招标签：", tone="info", raw=body)
    if body == "total drops:":
        return LogMessage(text="合计掉落：", tone="theme", raw=body, segments=[{"text": "合计掉落：", "tone": "theme", "strong": True}])
    if body.startswith("total drops: "):
        drops = replace_common_terms(body.removeprefix("total drops: "))
        return LogMessage(
            text=f"合计掉落: {drops}",
            tone="theme",
            raw=body,
            segments=[
                {"text": "合计掉落: ", "tone": "theme", "strong": True},
                {"text": drops},
            ],
        )

    count_match = SUMMARY_COUNT_RE.match(body)
    if count_match is not None:
        label = "已招募" if count_match.group("kind") == "Recruited" else "已刷新"
        return LogMessage(text=f"{label} {count_match.group('count')} 次", tone="info", raw=body)

    infrast_line = translate_infrast_summary_line(body)
    if infrast_line != body:
        return LogMessage(text=infrast_line, tone="info", raw=body)

    if body.startswith("Error:"):
        return LogMessage(text="存在失败任务，maa-cli 返回错误。", tone="danger", raw=body)
    if body.startswith("Warning:"):
        return LogMessage(text=body.replace("Warning:", "警告:", 1), tone="warning", raw=body)
    return LogMessage(text=replace_common_terms(body), tone="default")


def _translate_report_message(active: ActiveBlock, body: str) -> TranslatedMessage | None:
    is_report_start = body.startswith(("ReportToPenguinStats:", "ReportToYituliu:"))
    is_report_success = body in {"Successfully ReportToPenguinStats", "Successfully ReportToYituliu"}
    if not is_report_start and not is_report_success:
        return None

    if is_report_start or active.context.get("report_success_emitted"):
        return TranslatedMessage("", translated=True)

    active.context["report_success_emitted"] = True
    return TranslatedMessage("汇报成功", translated=True, tone="success")


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
    return translate_task_message(body).translated


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


def parse_log_line(raw: str) -> dict[str, str | None]:
    match = LOG_LINE_RE.match(raw)
    if match is None:
        return {"time": None, "level": None, "body": raw}
    return {
        "time": server_datetime_from_text(match.group("time")),
        "level": match.group("level"),
        "body": match.group("body"),
    }


def task_status(event: str) -> BlockStatus | None:
    if event == "Start":
        return "running"
    if event == "Completed":
        return "succeeded"
    if event == "Error":
        return "failed"
    if event == "Stopped":
        return "stopped"
    return None


def tone_for_status(status: BlockStatus) -> LogTone:
    if status == "succeeded":
        return "success"
    if status == "failed":
        return "danger"
    if status in {"stopped", "unknown", "unfinished", "warning"}:
        return "warning"
    return "info"


def is_stdout_resource_update_start(raw: str) -> bool:
    return raw == "Already up to date." or GIT_UPDATE_RE.match(raw) is not None


def is_stderr_fetch_start(raw: str, source: str) -> bool:
    return source.endswith(":stderr") and raw.startswith("From https://github.com/")


def _metadata_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _metadata_dict(metadata: dict[str, object], key: str) -> dict[str, object]:
    value = metadata.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _metadata_tone(metadata: dict[str, object], default: LogTone) -> LogTone:
    value = metadata.get("tone")
    return value if value in {"default", "success", "warning", "danger", "info", "theme"} else default


def _metadata_status(metadata: dict[str, object]) -> BlockStatus | None:
    value = metadata.get("status_override", metadata.get("status"))
    if value in {"default", "running", "succeeded", "failed", "stopped", "unknown", "unfinished", "warning"}:
        return value  # type: ignore[return-value]
    return None
