from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import ClassVar, Literal


TaskStatus = Literal["running", "succeeded", "failed", "stopped", "unknown"]
LogTone = Literal["default", "success", "warning", "danger", "info"]


_LOG_LINE_RE = re.compile(
    r"^\[(?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>[A-Z]+)\s*\]\s*(?P<body>.*)$"
)
_TASK_EVENT_RE = re.compile(
    r"^(?P<task>[A-Za-z][A-Za-z0-9_]*?)\s+"
    r"(?P<event>Start|Completed|Error|Stopped)\s*$"
)
_SUMMARY_TASK_RE = re.compile(
    r"^\[(?P<task>.+?)\]\s+"
    r"(?P<started>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+-\s+"
    r"(?P<ended>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"\((?P<elapsed>[^)]*)\)\s+"
    r"(?P<status>Completed|Error|Stopped|Unknown)\s*$"
)
_SUMMARY_FIGHT_DROPS_RE = re.compile(r"^Fight\s+(?P<stage>\S+)\s+(?P<times>\d+)\s+times,\s+drops:\s*$")

_EVENT_STATUS: dict[str, TaskStatus] = {
    "Start": "running",
    "Completed": "succeeded",
    "Error": "failed",
    "Stopped": "stopped",
}

_STATUS_LABEL: dict[TaskStatus, str] = {
    "running": "运行中",
    "succeeded": "成功",
    "failed": "失败",
    "stopped": "已停止",
    "unknown": "未确认结束",
}


_LEVEL_TONE: dict[str, LogTone] = {
    "ERROR": "danger",
    "WARN": "warning",
    "INFO": "info",
}


@dataclass
class MaaLogMessage:
    text: str
    time: str | None = None
    tone: LogTone = "default"
    raw: str | None = None
    segments: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "type": "text",
            "text": self.text,
            "tone": self.tone,
        }
        if self.time:
            data["time"] = self.time
        if self.raw:
            data["raw"] = self.raw
        if self.segments:
            data["segments"] = list(self.segments)
        return data

    def to_line_entry(self) -> dict[str, object]:
        data = self.to_dict()
        data["type"] = "line"
        return data


@dataclass(frozen=True)
class MaaLogPanelRule:
    """Configurable conditions for opening and closing a log panel."""

    id: str
    panel_kind: str
    event_pattern: re.Pattern[str]
    start_events: frozenset[str]
    end_status_by_event: dict[str, TaskStatus]
    name_group: str = "task"
    event_group: str = "event"

    def match(self, body: str) -> tuple[str, str, TaskStatus] | None:
        match = self.event_pattern.match(body)
        if match is None:
            return None

        name = match.group(self.name_group)
        event = match.group(self.event_group)
        if event in self.start_events:
            return name, event, "running"
        status = self.end_status_by_event.get(event)
        if status is None:
            return None
        return name, event, status


DEFAULT_PANEL_RULES: tuple[MaaLogPanelRule, ...] = (
    MaaLogPanelRule(
        id="maa-task-lifecycle",
        panel_kind="task",
        event_pattern=_TASK_EVENT_RE,
        start_events=frozenset({"Start"}),
        end_status_by_event={
            "Completed": "succeeded",
            "Error": "failed",
            "Stopped": "stopped",
        },
    ),
)


@dataclass
class MaaTaskLogRecord:
    name: str
    status: TaskStatus
    task_id: str | None = None
    source_name: str | None = None
    rule_id: str = "maa-task-lifecycle"
    panel_kind: str = "task"
    started_at: str | None = None
    ended_at: str | None = None
    messages: list[MaaLogMessage] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "type": "task",
            "name": self.name,
            "status": self.status,
            "rule_id": self.rule_id,
            "panel_kind": self.panel_kind,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "messages": [message.to_dict() for message in self.messages],
            "lines": list(self.lines),
        }
        if self.source_name and self.source_name != self.name:
            data["source_name"] = self.source_name
        if self.task_id:
            data["task_id"] = self.task_id
        return data


@dataclass
class MaaSummaryLogRecord:
    status: TaskStatus = "succeeded"
    title: str = "运行摘要"
    messages: list[MaaLogMessage] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "summary",
            "title": self.title,
            "status": self.status,
            "messages": [message.to_dict() for message in self.messages],
            "lines": list(self.lines),
        }


@dataclass
class MaaCliLogTranslator:
    """Stateful translator for maa-cli's user-facing log stream."""

    panel_rules: ClassVar[tuple[MaaLogPanelRule, ...]] = DEFAULT_PANEL_RULES

    task_records: list[MaaTaskLogRecord] = field(default_factory=list)
    log_entries: list[MaaTaskLogRecord | MaaSummaryLogRecord | MaaLogMessage] = field(default_factory=list)
    _current: MaaTaskLogRecord | None = None
    _current_summary: MaaSummaryLogRecord | None = None
    _current_started_monotonic: float | None = None
    _expected_tasks: list[dict[str, str]] = field(default_factory=list)
    _expected_task_index: int = 0
    _partial: str = ""

    def translate(self, text: str) -> str:
        if not text:
            return ""

        text = self._partial + text
        self._partial = ""

        chunks = text.splitlines(keepends=True)
        if chunks and not chunks[-1].endswith(("\n", "\r")):
            self._partial = chunks.pop()

        return "".join(self._translate_line(chunk) for chunk in chunks)

    def flush(self) -> str:
        output = ""
        if self._partial:
            output += self._translate_line(self._partial)
            self._partial = ""
        if self._current is not None:
            output += self._close_current("unknown")
        self._current_summary = None
        return output

    def task_results(self) -> list[dict[str, object]]:
        return [record.to_dict() for record in self.task_records]

    def entries(self) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        for entry in self.log_entries:
            if isinstance(entry, MaaTaskLogRecord):
                entries.append(entry.to_dict())
            elif isinstance(entry, MaaSummaryLogRecord):
                entries.append(entry.to_dict())
            else:
                entries.append(entry.to_line_entry())
        return entries

    def add_event(
        self,
        text: str,
        *,
        time: str | None = None,
        tone: LogTone = "info",
        segments: list[dict[str, object]] | None = None,
    ) -> str:
        message = MaaLogMessage(text=text, time=time, tone=tone, segments=segments or [])
        self.log_entries.append(message)
        return f"{_format_time_prefix(time)}{text}\n"

    def begin_task_sequence(self, tasks: list[dict[str, str]]) -> None:
        self._expected_tasks = [
            {
                "task_id": str(task.get("task_id") or ""),
                "source_name": str(task.get("source_name") or task.get("type") or task.get("name") or ""),
                "name": str(task.get("name") or task.get("source_name") or task.get("type") or ""),
            }
            for task in tasks
            if task.get("source_name") or task.get("type") or task.get("name")
        ]
        self._expected_task_index = 0

    def current_task_elapsed_seconds(self) -> tuple[str, float] | None:
        if self._current is None or self._current_started_monotonic is None:
            return None
        return self._current.name, time.monotonic() - self._current_started_monotonic

    def _translate_line(self, line: str) -> str:
        raw = line.rstrip("\r\n")
        parsed = _parse_log_line(raw)
        body = parsed["body"]

        if parsed["time"] is not None and self._current_summary is not None:
            self._current_summary = None

        if body == "Summary":
            output = ""
            if self._current is not None:
                output += self._close_current("unknown")
            record = MaaSummaryLogRecord(lines=[raw])
            self.log_entries.append(record)
            self._current_summary = record
            return f"{output}运行摘要\n"

        if self._current_summary is not None and parsed["time"] is None:
            message = _translate_summary_message(body)
            self._current_summary.lines.append(raw)
            if message is None:
                return ""
            self._current_summary.messages.append(message)
            if message.tone == "danger":
                self._current_summary.status = "failed"
            elif message.tone == "warning" and self._current_summary.status != "failed":
                self._current_summary.status = "stopped"
            return f"{message.text}\n"

        panel_event = self._match_panel_event(body)
        if panel_event is None:
            if self._current is None:
                translated = _translate_global_message(body)
                message = MaaLogMessage(
                    text=translated.text,
                    time=parsed["time"],
                    tone=translated.tone or parsed["tone"],
                    raw=None if translated.translated else raw,
                    segments=translated.segments,
                )
                self.log_entries.append(message)
                return f"{_format_time_prefix(message.time)}{message.text}\n"
            message = MaaLogMessage(
                text=_translate_task_line(body),
                time=parsed["time"],
                tone=parsed["tone"],
                raw=None if _is_task_line_translated(body) else raw,
            )
            self._current.messages.append(message)
            self._current.lines.append(raw)
            return f"{_format_time_prefix(message.time)}{message.text}\n"

        rule, task_name, event, status = panel_event

        if status == "running":
            output = ""
            if self._current is not None:
                output += self._close_current("unknown")
            expected_task = self._next_expected_task(task_name)
            display_name = expected_task.get("name") or task_name
            record = MaaTaskLogRecord(
                name=display_name,
                status="running",
                task_id=expected_task.get("task_id") or None,
                source_name=task_name,
                rule_id=rule.id,
                panel_kind=rule.panel_kind,
                started_at=parsed["time"],
                lines=[raw],
            )
            self.task_records.append(record)
            self.log_entries.append(record)
            self._current = record
            self._current_started_monotonic = time.monotonic()
            return f"{output}{_format_time_prefix(parsed['time'])}已开始任务: {display_name}\n"

        if self._current is None or (self._current.source_name or self._current.name) != task_name:
            output = ""
            if self._current is not None:
                output += self._close_current("unknown")
            expected_task = self._next_expected_task(task_name)
            display_name = expected_task.get("name") or task_name
            record = MaaTaskLogRecord(
                name=display_name,
                status=status,
                task_id=expected_task.get("task_id") or None,
                source_name=task_name,
                rule_id=rule.id,
                panel_kind=rule.panel_kind,
                ended_at=parsed["time"],
                lines=[raw],
            )
            self.task_records.append(record)
            self.log_entries.append(record)
            return f"{output}{_format_time_prefix(parsed['time'])}任务 {display_name} {_STATUS_LABEL[status]}\n"

        self._current.lines.append(raw)
        self._current.status = status
        self._current.ended_at = parsed["time"]
        return self._close_current(status)

    def _match_panel_event(self, body: str) -> tuple[MaaLogPanelRule, str, str, TaskStatus] | None:
        for rule in self.panel_rules:
            matched = rule.match(body)
            if matched is not None:
                name, event, status = matched
                return rule, name, event, status
        return None

    def _close_current(self, status: TaskStatus) -> str:
        if self._current is None:
            return ""
        self._current.status = status
        task_name = self._current.name
        ended_at = self._current.ended_at or self._current.started_at
        self._current = None
        self._current_started_monotonic = None
        return f"{_format_time_prefix(ended_at)}任务 {task_name} {_STATUS_LABEL[status]}\n"

    def _next_expected_task(self, source_name: str) -> dict[str, str]:
        for index in range(self._expected_task_index, len(self._expected_tasks)):
            task = self._expected_tasks[index]
            if task.get("source_name") != source_name:
                continue
            self._expected_task_index = index + 1
            return task
        return {"task_id": "", "source_name": source_name, "name": source_name}


def translate_maa_cli_log(text: str) -> str:
    """Backward-compatible one-shot translation helper."""

    translator = MaaCliLogTranslator()
    return translator.translate(text) + translator.flush()


def _parse_log_line(raw: str) -> dict[str, str | LogTone | None]:
    match = _LOG_LINE_RE.match(raw)
    if match is None:
        return {"time": None, "level": None, "body": raw, "tone": "default"}
    level = match.group("level")
    return {
        "time": match.group("time")[-8:],
        "level": level,
        "body": match.group("body"),
        "tone": _LEVEL_TONE.get(level, "default"),
    }


def _format_time_prefix(time_text: str | None) -> str:
    return f"{time_text} " if time_text else ""


def _translate_global_line(body: str) -> str:
    return _translate_global_message(body).text


@dataclass(frozen=True)
class TranslatedMessage:
    text: str
    translated: bool = False
    tone: LogTone | None = None
    segments: list[dict[str, object]] = field(default_factory=list)


def _translate_global_message(body: str) -> TranslatedMessage:
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


def _translate_task_line(body: str) -> str:
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


def _translate_summary_message(body: str) -> MaaLogMessage | None:
    if not body or body == "----------------------------------------":
        return None

    task_match = _SUMMARY_TASK_RE.match(body)
    if task_match is not None:
        task_name = task_match.group("task")
        elapsed = task_match.group("elapsed")
        status = task_match.group("status")
        status_label, tone = _summary_status(status)
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

    fight_match = _SUMMARY_FIGHT_DROPS_RE.match(body)
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


def _summary_status(status: str) -> tuple[str, LogTone]:
    if status == "Completed":
        return "完成", "success"
    if status == "Error":
        return "失败", "danger"
    if status == "Stopped":
        return "已停止", "warning"
    return "未确认结束", "warning"


def _is_global_line_translated(body: str) -> bool:
    return _translate_global_message(body).translated


def _is_task_line_translated(body: str) -> bool:
    return _translate_task_line(body) != body
