from __future__ import annotations

import re
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

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


@dataclass
class MaaCliLogTranslator:
    """Stateful translator for maa-cli's user-facing log stream."""

    panel_rules: ClassVar[tuple[LogRule, ...]] = DEFAULT_PANEL_RULES

    max_log_entries: int = 1000
    max_task_records: int = 500
    max_record_messages: int = 300
    max_record_lines: int = 300
    terminal_update_interval_seconds: float = 2.0
    task_records: list[MaaTaskLogRecord] = field(default_factory=list)
    log_entries: list[LogEntry] = field(default_factory=list)
    _current_by_source: dict[str, MaaTaskLogRecord] = field(default_factory=dict)
    _current_summary_by_source: dict[str, MaaSummaryLogRecord] = field(default_factory=dict)
    _current_git_block_by_source: dict[str, MaaSummaryLogRecord] = field(default_factory=dict)
    _current_started_monotonic_by_source: dict[str, float] = field(default_factory=dict)
    _expected_tasks: list[dict[str, str]] = field(default_factory=list)
    _expected_task_index: int = 0
    _partial_by_source: dict[str, str] = field(default_factory=dict)
    _terminal_entry_by_source: dict[str, MaaLogMessage] = field(default_factory=dict)
    _terminal_last_emit_by_source: dict[str, float] = field(default_factory=dict)
    _terminal_last_output_by_source: dict[str, str] = field(default_factory=dict)

    def translate(self, text: str, *, source: str = "output") -> str:
        if not text:
            return ""

        source_key = normalize_source(source)
        text = self._partial_by_source.get(source_key, "") + text
        self._partial_by_source.pop(source_key, None)
        return self._translate_text(text, source_key)

    def flush(self, *, source: str | None = None) -> str:
        output = ""
        sources = [normalize_source(source)] if source is not None else self._active_sources()
        for source_key in sources:
            partial = self._partial_by_source.pop(source_key, "")
            if partial:
                if source_key in self._terminal_entry_by_source:
                    output += self._handle_terminal_update(partial, source_key, final=True)
                else:
                    output += self._translate_line(partial, source_key)
            if source_key in self._terminal_entry_by_source:
                output += self._finalize_terminal_update(source_key)
            if source_key in self._current_by_source:
                output += self._close_current("unknown", source_key)
            self._current_summary_by_source.pop(source_key, None)
            self._current_git_block_by_source.pop(source_key, None)
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
        self._append_entry(message)
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
        if not self._current_by_source or not self._current_started_monotonic_by_source:
            return None
        active = [
            (started, self._current_by_source[source])
            for source, started in self._current_started_monotonic_by_source.items()
            if source in self._current_by_source
        ]
        if not active:
            return None
        started, record = max(active, key=lambda item: item[0])
        return record.name, time.monotonic() - started

    def _translate_text(self, text: str, source: str) -> str:
        output = ""
        line = ""
        index = 0
        while index < len(text):
            char = text[index]
            if char == "\r":
                if index + 1 < len(text) and text[index + 1] == "\n":
                    output += self._translate_line(line, source)
                    line = ""
                    index += 2
                    continue
                output += self._handle_terminal_update(line, source)
                line = ""
            elif char == "\n":
                if source in self._terminal_entry_by_source:
                    if line:
                        output += self._handle_terminal_update(line, source, final=True)
                    output += self._finalize_terminal_update(source)
                else:
                    output += self._translate_line(line, source)
                line = ""
            elif char in {"\b", "\x7f"}:
                line = line[:-1]
            else:
                line += char
            index += 1

        if line:
            self._partial_by_source[source] = line
        return output

    def _translate_line(self, line: str, source: str) -> str:
        raw = line.rstrip("\r\n")
        parsed = parse_log_line(raw)
        rule_match = match_log_rule(parsed, self.panel_rules)

        if source in self._current_git_block_by_source:
            if parsed["time"] is None and rule_match.kind == "line" and not is_git_output_start(raw):
                return self._handle_git_output_line(raw, source)
            self._current_git_block_by_source.pop(source, None)

        if parsed["time"] is not None:
            self._current_summary_by_source.pop(source, None)

        if parsed["time"] is None and is_git_output_start(raw):
            self._current_summary_by_source.pop(source, None)
            return self._handle_git_output_start(raw, source)

        if rule_match.kind == "summary":
            return self._handle_summary_start(raw, source)

        if source in self._current_summary_by_source and parsed["time"] is None:
            return self._handle_summary_line(raw, parsed, source)

        if rule_match.kind == "task":
            return self._handle_task_event(raw, parsed, rule_match, source)

        return self._handle_default_line(raw, parsed, source)

    def _handle_terminal_update(self, raw: str, source: str, *, final: bool = False) -> str:
        text = terminal_display_text(raw)
        if not text:
            return ""

        message = self._terminal_entry_by_source.get(source)
        first_update = message is None
        if message is None:
            message = MaaLogMessage(text=text, tone="info", raw=text)
            self._append_entry(message)
            self._terminal_entry_by_source[source] = message
        else:
            message.text = text
            message.raw = text

        now = time.monotonic()
        last_emit = self._terminal_last_emit_by_source.get(source, 0)
        should_emit = first_update or final or now - last_emit >= self.terminal_update_interval_seconds
        if should_emit:
            self._terminal_last_emit_by_source[source] = now
            self._terminal_last_output_by_source[source] = text
            return f"{text}\n"
        return ""

    def _finalize_terminal_update(self, source: str) -> str:
        message = self._terminal_entry_by_source.pop(source, None)
        self._terminal_last_emit_by_source.pop(source, None)
        last_output = self._terminal_last_output_by_source.pop(source, "")
        if message is None:
            return ""
        return f"{message.text}\n" if message.text != last_output else ""

    def _handle_summary_start(self, raw: str, source: str) -> str:
        output = ""
        if source in self._current_by_source:
            output += self._close_current("unknown", source)
        record = MaaSummaryLogRecord(lines=[raw])
        self._append_entry(record)
        self._current_summary_by_source[source] = record
        return f"{output}运行摘要\n"

    def _handle_summary_line(self, raw: str, parsed: ParsedLine, source: str) -> str:
        record = self._current_summary_by_source[source]
        body = str(parsed["body"] or "")
        message = translate_summary_message(body)
        record.lines.append(raw)
        if message is None:
            self._trim_record(record)
            return ""
        record.messages.append(message)
        self._trim_record(record)
        if message.tone == "danger":
            record.status = "failed"
        elif message.tone == "warning" and record.status != "failed":
            record.status = "stopped"
        return f"{message.text}\n"

    def _handle_git_output_start(self, raw: str, source: str) -> str:
        record = MaaSummaryLogRecord(title="资源拉取结果", lines=[raw])
        self._append_entry(record)
        self._current_git_block_by_source[source] = record
        return "资源拉取结果\n" + self._handle_git_output_line(raw, source)

    def _handle_git_output_line(self, raw: str, source: str) -> str:
        record = self._current_git_block_by_source[source]
        message = MaaLogMessage(text=raw, tone="info", raw=raw)
        record.messages.append(message)
        if not record.lines or record.lines[-1] != raw:
            record.lines.append(raw)
        self._trim_record(record)
        return f"{raw}\n"

    def _handle_task_event(self, raw: str, parsed: ParsedLine, matched: LogRuleMatch, source: str) -> str:
        task_name = matched.name
        status = matched.status or "unknown"
        if status == "running":
            output = ""
            if source in self._current_by_source:
                output += self._close_current("unknown", source)
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
            self._append_task_record(record)
            self._current_by_source[source] = record
            self._current_started_monotonic_by_source[source] = time.monotonic()
            return f"{output}{format_time_prefix(parsed['time'])}已开始任务: {display_name}\n"

        current = self._current_by_source.get(source)
        if current is None or (current.source_name or current.name) != task_name:
            return self._record_unmatched_task_end(raw, parsed, matched, task_name, status, source)

        current.lines.append(raw)
        self._trim_record(current)
        current.status = status
        current.ended_at = parsed["time"]
        return self._close_current(status, source)

    def _record_unmatched_task_end(
        self,
        raw: str,
        parsed: ParsedLine,
        matched: LogRuleMatch,
        task_name: str,
        status: TaskStatus,
        source: str,
    ) -> str:
        output = ""
        if source in self._current_by_source:
            output += self._close_current("unknown", source)
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
        self._append_task_record(record)
        return f"{output}{format_time_prefix(parsed['time'])}任务 {display_name} {STATUS_LABEL[status]}\n"

    def _handle_default_line(self, raw: str, parsed: ParsedLine, source: str) -> str:
        body = str(parsed["body"] or "")
        time_text = parsed["time"]
        level = parsed["level"]
        tone = LEVEL_TONE.get(str(level), "default") if level is not None else "default"

        current = self._current_by_source.get(source)
        if current is None:
            translated = translate_global_message(body)
            message = MaaLogMessage(
                text=translated.text,
                time=time_text,
                tone=translated.tone or tone,
                raw=None if translated.translated else raw,
                segments=translated.segments,
            )
            self._append_entry(message)
            return f"{format_time_prefix(message.time)}{message.text}\n"

        translated_task_line = translate_task_line(body)
        current.lines.append(raw)
        if translated_task_line is None:
            self._trim_record(current)
            return ""
        message = MaaLogMessage(
            text=translated_task_line,
            time=time_text,
            tone=tone,
            raw=None if is_task_line_translated(body) else raw,
        )
        current.messages.append(message)
        self._trim_record(current)
        return f"{format_time_prefix(message.time)}{message.text}\n"

    def _close_current(self, status: TaskStatus, source: str) -> str:
        current = self._current_by_source.pop(source, None)
        if current is None:
            return ""
        current.status = status
        task_name = current.name
        ended_at = current.ended_at or current.started_at
        self._current_started_monotonic_by_source.pop(source, None)
        return f"{format_time_prefix(ended_at)}任务 {task_name} {STATUS_LABEL[status]}\n"

    def _append_task_record(self, record: MaaTaskLogRecord) -> None:
        self.task_records.append(record)
        self._append_entry(record)

    def _append_entry(self, entry: LogEntry) -> None:
        self.log_entries.append(entry)
        self._trim()

    def _trim(self) -> None:
        _trim_list(self.log_entries, self.max_log_entries)
        _trim_list(self.task_records, self.max_task_records)
        for entry in self.log_entries:
            if isinstance(entry, MaaTaskLogRecord | MaaSummaryLogRecord):
                self._trim_record(entry)
        for record in self.task_records:
            self._trim_record(record)

    def _trim_record(self, record: MaaTaskLogRecord | MaaSummaryLogRecord) -> None:
        _trim_list(record.messages, self.max_record_messages)
        _trim_list(record.lines, self.max_record_lines)

    def _next_expected_task(self, source_name: str) -> dict[str, str]:
        for index in range(self._expected_task_index, len(self._expected_tasks)):
            task = self._expected_tasks[index]
            if task.get("source_name") != source_name:
                continue
            self._expected_task_index = index + 1
            return task
        return {"task_id": "", "source_name": source_name, "name": source_name}

    def _active_sources(self) -> list[str]:
        sources: dict[str, None] = {}
        for mapping in (
            self._partial_by_source,
            self._terminal_entry_by_source,
            self._current_by_source,
            self._current_summary_by_source,
            self._current_git_block_by_source,
        ):
            for source in mapping:
                sources[source] = None
        return list(sources)


def translate_maa_cli_log(text: str) -> str:
    """Backward-compatible one-shot translation helper."""

    translator = MaaCliLogTranslator()
    return translator.translate(text) + translator.flush()


def format_time_prefix(time_text: str | None) -> str:
    return f"{time_text} " if time_text else ""


def normalize_source(source: str | None) -> str:
    return "stderr" if source == "stderr" else "stdout"


GIT_UPDATE_RE = re.compile(r"^Updating [0-9a-f]{4,}\.\.[0-9a-f]{4,}$")


def is_git_output_start(raw: str) -> bool:
    return raw.startswith("From https://github.com/") or raw == "Already up to date." or GIT_UPDATE_RE.match(raw) is not None


def terminal_display_text(raw: str) -> str:
    return ANSI_ESCAPE_RE.sub("", raw).strip()


def _trim_list(values: list[object], max_items: int) -> None:
    if max_items < 0:
        return
    overflow = len(values) - max_items
    if overflow > 0:
        del values[:overflow]


def _translate_global_line(body: str) -> str:
    return translate_global_message(body).text


def _is_global_line_translated(body: str) -> bool:
    return is_global_line_translated(body)


def _is_task_line_translated(body: str) -> bool:
    return is_task_line_translated(body)
