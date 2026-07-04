from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from linux_maa.logs.pipeline import LogPipelineSession, format_time_prefix
from linux_maa.logs.records import LogEntry, LogMessage, LogTone, TaskStatus


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

STATUS_LABEL: dict[TaskStatus, str] = {
    "running": "运行中",
    "succeeded": "成功",
    "failed": "失败",
    "stopped": "已停止",
    "unknown": "未确认结束",
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
class MaaLogTemplate:
    """MAA-specific block assembly and message translation template."""

    expected_tasks: list[dict[str, str]] = field(default_factory=list)
    expected_task_index: int = 0
    current_by_source: dict[str, LogEntry] = field(default_factory=dict)
    current_summary_by_source: dict[str, LogEntry] = field(default_factory=dict)
    current_git_block_by_source: dict[str, LogEntry] = field(default_factory=dict)
    task_records: list[LogEntry] = field(default_factory=list)
    max_task_records: int = 500

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

    def handle_line(self, session: LogPipelineSession, source: str, raw: str) -> str:
        raw = raw.rstrip("\r\n")
        parsed = parse_log_line(raw)

        if source in self.current_git_block_by_source:
            if parsed["body"] == "Summary":
                self.current_git_block_by_source.pop(source, None)
            elif parsed["time"] is None:
                return self._handle_git_output_line(session, raw, source)
            else:
                self.current_git_block_by_source.pop(source, None)

        if parsed["time"] is not None:
            self.current_summary_by_source.pop(source, None)

        if parsed["time"] is None and is_stderr_fetch_start(raw, source):
            self.current_summary_by_source.pop(source, None)
            return self._handle_git_output_start(session, raw, source, title="资源拉取诊断")

        if parsed["time"] is None and is_stdout_resource_update_start(raw):
            self.current_summary_by_source.pop(source, None)
            return self._handle_git_output_start(session, raw, source)

        if parsed["body"] == "Summary":
            return self._handle_summary_start(session, raw, source)

        if source in self.current_summary_by_source and parsed["time"] is None:
            return self._handle_summary_line(raw, parsed, source)

        task_match = TASK_EVENT_RE.match(str(parsed["body"] or ""))
        if task_match is not None:
            status = task_status(task_match.group("event"))
            if status is not None:
                return self._handle_task_event(session, raw, parsed, source, task_match.group("task"), status)

        return self._handle_default_line(session, raw, parsed, source)

    def flush_source(self, session: LogPipelineSession, source: str) -> str:
        output = ""
        if source in self.current_by_source:
            output += self._close_current("unknown", source)
        self.current_summary_by_source.pop(source, None)
        self.current_git_block_by_source.pop(source, None)
        return output

    def task_results(self, *, max_items: int = 500) -> list[dict[str, object]]:
        return [task_entry_to_result(record) for record in self.task_records][-max_items:]

    def current_block_elapsed_seconds(self, *, kind: str | None = None) -> tuple[str, float] | None:
        if kind not in {None, "task"}:
            return None
        active = [
            (float(started), record)
            for record in self.current_by_source.values()
            for started in [record.metadata.get("started_monotonic")]
            if isinstance(started, (int, float))
        ]
        if not active:
            return None
        started, record = max(active, key=lambda item: item[0])
        return record.name or record.title, time.monotonic() - started

    def _handle_summary_start(self, session: LogPipelineSession, raw: str, source: str) -> str:
        output = ""
        if source in self.current_by_source:
            output += self._close_current("unknown", source)
        record = session.append_block(
            source,
            kind="summary",
            title="运行摘要",
            status="succeeded",
            tone="success",
            lines=[raw],
        )
        self.current_summary_by_source[source] = record
        return f"{output}运行摘要\n"

    def _handle_summary_line(self, raw: str, parsed: dict[str, str | None], source: str) -> str:
        record = self.current_summary_by_source[source]
        body = str(parsed["body"] or "")
        message = translate_summary_message(body)
        record.lines.append(raw)
        if message is None:
            return ""
        record.messages.append(message)
        if message.tone == "danger":
            record.status = "failed"
            record.tone = "danger"
        elif message.tone == "warning" and record.status != "failed":
            record.status = "stopped"
            record.tone = "warning"
        return f"{message.text}\n"

    def _handle_git_output_start(self, session: LogPipelineSession, raw: str, source: str, *, title: str = "资源拉取结果") -> str:
        record = session.append_block(
            source,
            kind="summary",
            title=title,
            status="succeeded",
            tone="info",
            lines=[raw],
        )
        self.current_git_block_by_source[source] = record
        return f"{title}\n" + self._handle_git_output_line(session, raw, source)

    def _handle_git_output_line(self, session: LogPipelineSession, raw: str, source: str) -> str:
        record = self.current_git_block_by_source[source]
        message = LogMessage(text=raw, tone="info", raw=raw)
        record.messages.append(message)
        if not record.lines or record.lines[-1] != raw:
            record.lines.append(raw)
        return f"{raw}\n"

    def _handle_task_event(
        self,
        session: LogPipelineSession,
        raw: str,
        parsed: dict[str, str | None],
        source: str,
        task_name: str,
        status: TaskStatus,
    ) -> str:
        if status == "running":
            output = ""
            if source in self.current_by_source:
                output += self._close_current("unknown", source)
            expected_task = self._next_expected_task(task_name)
            display_name = expected_task.get("name") or task_name
            record = session.append_block(
                source,
                kind="task",
                title=f"任务 {display_name}",
                status="running",
                started_at=parsed["time"],
                tone="info",
                lines=[raw],
                name=display_name,
                task_id=expected_task.get("task_id") or None,
                source_name=task_name,
                rule_id="maa-task-lifecycle",
                panel_kind="task",
                metadata={"started_monotonic": time.monotonic()},
            )
            self.current_by_source[source] = record
            self._append_task_record(record)
            return f"{output}{format_time_prefix(parsed['time'])}已开始任务: {display_name}\n"

        current = self.current_by_source.get(source)
        if current is None or (current.source_name or current.name) != task_name:
            return self._record_unmatched_task_end(session, raw, parsed, task_name, status, source)

        current.lines.append(raw)
        current.status = status
        current.ended_at = parsed["time"]
        return self._close_current(status, source)

    def _record_unmatched_task_end(
        self,
        session: LogPipelineSession,
        raw: str,
        parsed: dict[str, str | None],
        task_name: str,
        status: TaskStatus,
        source: str,
    ) -> str:
        output = ""
        if source in self.current_by_source:
            output += self._close_current("unknown", source)
        expected_task = self._next_expected_task(task_name)
        display_name = expected_task.get("name") or task_name
        record = session.append_block(
            source,
            kind="task",
            title=f"任务 {display_name}",
            status=status,
            ended_at=parsed["time"],
            tone=tone_for_status(status),
            lines=[raw],
            name=display_name,
            task_id=expected_task.get("task_id") or None,
            source_name=task_name,
            rule_id="maa-task-lifecycle",
            panel_kind="task",
        )
        self._append_task_record(record)
        return f"{output}{format_time_prefix(parsed['time'])}任务 {display_name} {STATUS_LABEL[status]}\n"

    def _handle_default_line(self, session: LogPipelineSession, raw: str, parsed: dict[str, str | None], source: str) -> str:
        body = str(parsed["body"] or "")
        time_text = parsed["time"]
        level = parsed["level"]
        tone = LEVEL_TONE.get(str(level), "default") if level is not None else session.source_spec(source).default_tone

        current = self.current_by_source.get(source)
        if current is None:
            translated = translate_global_message(body)
            message = LogMessage(
                text=translated.text,
                time=time_text,
                tone=translated.tone or tone,
                raw=None if translated.translated else raw,
                segments=translated.segments,
            )
            session.append_block(
                source,
                kind="line",
                time=time_text,
                tone=message.tone,
                messages=[message],
                lines=[raw],
                raw=None if translated.translated else raw,
            )
            return f"{format_time_prefix(message.time)}{message.text}\n"

        translated_task_line = translate_task_line(body)
        current.lines.append(raw)
        if translated_task_line is None:
            return ""
        message = LogMessage(
            text=translated_task_line,
            time=time_text,
            tone=tone,
            raw=None if is_task_line_translated(body) else raw,
        )
        current.messages.append(message)
        return f"{format_time_prefix(message.time)}{message.text}\n"

    def _close_current(self, status: TaskStatus, source: str) -> str:
        current = self.current_by_source.pop(source, None)
        if current is None:
            return ""
        current.status = status
        current.tone = tone_for_status(status)
        current.metadata.pop("started_monotonic", None)
        task_name = current.name or current.title
        ended_at = current.ended_at or current.started_at
        return f"{format_time_prefix(ended_at)}任务 {task_name} {STATUS_LABEL[status]}\n"

    def _next_expected_task(self, source_name: str) -> dict[str, str]:
        for index in range(self.expected_task_index, len(self.expected_tasks)):
            task = self.expected_tasks[index]
            if task.get("source_name") != source_name:
                continue
            self.expected_task_index = index + 1
            return task
        return {"task_id": "", "source_name": source_name, "name": source_name}

    def _append_task_record(self, record: LogEntry) -> None:
        self.task_records.append(record)
        overflow = len(self.task_records) - self.max_task_records
        if overflow > 0:
            del self.task_records[:overflow]


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
        return LogMessage(
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
        return LogMessage(text="识别到的公招标签：", tone="info", raw=body)
    if body == "total drops:":
        return LogMessage(text="合计掉落：", tone="info", raw=body)
    if body.startswith("total drops: "):
        return LogMessage(text=replace_common_terms(body.replace("total drops", "合计掉落", 1)), tone="info", raw=body)

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


def parse_log_line(raw: str) -> dict[str, str | None]:
    match = LOG_LINE_RE.match(raw)
    if match is None:
        return {"time": None, "level": None, "body": raw}
    return {
        "time": match.group("time")[-8:],
        "level": match.group("level"),
        "body": match.group("body"),
    }


def task_status(event: str) -> TaskStatus | None:
    if event == "Start":
        return "running"
    if event == "Completed":
        return "succeeded"
    if event == "Error":
        return "failed"
    if event == "Stopped":
        return "stopped"
    return None


def tone_for_status(status: TaskStatus) -> LogTone:
    if status == "succeeded":
        return "success"
    if status == "failed":
        return "danger"
    if status in {"stopped", "unknown"}:
        return "warning"
    return "info"


def is_stdout_resource_update_start(raw: str) -> bool:
    return raw == "Already up to date." or GIT_UPDATE_RE.match(raw) is not None


def is_stderr_fetch_start(raw: str, source: str) -> bool:
    return source.endswith(":stderr") and raw.startswith("From https://github.com/")


def task_entry_to_result(record: LogEntry) -> dict[str, object]:
    return {
        key: value
        for key, value in {
            "type": "task",
            "name": record.name or record.title,
            "task_id": record.task_id,
            "source_name": record.source_name,
            "status": record.status or "unknown",
            "rule_id": record.rule_id,
            "panel_kind": record.panel_kind,
            "started_at": record.started_at,
            "ended_at": record.ended_at,
            "messages": [message.to_dict() for message in record.messages],
            "lines": list(record.lines),
        }.items()
        if value is not None
    }
