from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import ClassVar

from linux_maa.maa.logs.records import (
    LogEntry,
    LogTone,
    MaaLogMessage,
    MaaSummaryLogRecord,
    MaaTaskLogRecord,
    TaskStatus,
)
from linux_maa.maa.logs.rules import DEFAULT_PANEL_RULES, LogRule, LogRuleMatch, ParsedLine, match_log_rule, parse_log_line
from linux_maa.maa.logs.translation import (
    is_global_line_translated,
    is_task_line_translated,
    translate_global_message,
    translate_summary_message,
    translate_task_line,
)


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


@dataclass
class MaaCliLogTranslator:
    """Stateful translator for maa-cli's user-facing log stream."""

    panel_rules: ClassVar[tuple[LogRule, ...]] = DEFAULT_PANEL_RULES

    task_records: list[MaaTaskLogRecord] = field(default_factory=list)
    log_entries: list[LogEntry] = field(default_factory=list)
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
        return f"{format_time_prefix(time)}{text}\n"

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
        parsed = parse_log_line(raw)
        rule_match = match_log_rule(parsed, self.panel_rules)

        if parsed["time"] is not None and self._current_summary is not None:
            self._current_summary = None

        if rule_match.kind == "summary":
            return self._handle_summary_start(raw)

        if self._current_summary is not None and parsed["time"] is None:
            return self._handle_summary_line(raw, parsed)

        if rule_match.kind == "task":
            return self._handle_task_event(raw, parsed, rule_match)

        return self._handle_default_line(raw, parsed)

    def _handle_summary_start(self, raw: str) -> str:
        output = ""
        if self._current is not None:
            output += self._close_current("unknown")
        record = MaaSummaryLogRecord(lines=[raw])
        self.log_entries.append(record)
        self._current_summary = record
        return f"{output}运行摘要\n"

    def _handle_summary_line(self, raw: str, parsed: ParsedLine) -> str:
        assert self._current_summary is not None
        body = str(parsed["body"] or "")
        message = translate_summary_message(body)
        self._current_summary.lines.append(raw)
        if message is None:
            return ""
        self._current_summary.messages.append(message)
        if message.tone == "danger":
            self._current_summary.status = "failed"
        elif message.tone == "warning" and self._current_summary.status != "failed":
            self._current_summary.status = "stopped"
        return f"{message.text}\n"

    def _handle_task_event(self, raw: str, parsed: ParsedLine, matched: LogRuleMatch) -> str:
        task_name = matched.name
        status = matched.status or "unknown"
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
                rule_id=matched.rule_id,
                panel_kind=matched.panel_kind,
                started_at=parsed["time"],
                lines=[raw],
            )
            self.task_records.append(record)
            self.log_entries.append(record)
            self._current = record
            self._current_started_monotonic = time.monotonic()
            return f"{output}{format_time_prefix(parsed['time'])}已开始任务: {display_name}\n"

        if self._current is None or (self._current.source_name or self._current.name) != task_name:
            return self._record_unmatched_task_end(raw, parsed, matched, task_name, status)

        self._current.lines.append(raw)
        self._current.status = status
        self._current.ended_at = parsed["time"]
        return self._close_current(status)

    def _record_unmatched_task_end(
        self,
        raw: str,
        parsed: ParsedLine,
        matched: LogRuleMatch,
        task_name: str,
        status: TaskStatus,
    ) -> str:
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
            rule_id=matched.rule_id,
            panel_kind=matched.panel_kind,
            ended_at=parsed["time"],
            lines=[raw],
        )
        self.task_records.append(record)
        self.log_entries.append(record)
        return f"{output}{format_time_prefix(parsed['time'])}任务 {display_name} {STATUS_LABEL[status]}\n"

    def _handle_default_line(self, raw: str, parsed: ParsedLine) -> str:
        body = str(parsed["body"] or "")
        time_text = parsed["time"]
        level = parsed["level"]
        tone = LEVEL_TONE.get(str(level), "default") if level is not None else "default"

        if self._current is None:
            translated = translate_global_message(body)
            message = MaaLogMessage(
                text=translated.text,
                time=time_text,
                tone=translated.tone or tone,
                raw=None if translated.translated else raw,
                segments=translated.segments,
            )
            self.log_entries.append(message)
            return f"{format_time_prefix(message.time)}{message.text}\n"

        message = MaaLogMessage(
            text=translate_task_line(body),
            time=time_text,
            tone=tone,
            raw=None if is_task_line_translated(body) else raw,
        )
        self._current.messages.append(message)
        self._current.lines.append(raw)
        return f"{format_time_prefix(message.time)}{message.text}\n"

    def _close_current(self, status: TaskStatus) -> str:
        if self._current is None:
            return ""
        self._current.status = status
        task_name = self._current.name
        ended_at = self._current.ended_at or self._current.started_at
        self._current = None
        self._current_started_monotonic = None
        return f"{format_time_prefix(ended_at)}任务 {task_name} {STATUS_LABEL[status]}\n"

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


def format_time_prefix(time_text: str | None) -> str:
    return f"{time_text} " if time_text else ""


def _translate_global_line(body: str) -> str:
    return translate_global_message(body).text


def _is_global_line_translated(body: str) -> bool:
    return is_global_line_translated(body)


def _is_task_line_translated(body: str) -> bool:
    return is_task_line_translated(body)
