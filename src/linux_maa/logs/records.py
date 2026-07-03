from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


TaskStatus = Literal["running", "succeeded", "failed", "stopped", "unknown"]
LogTone = Literal["default", "success", "warning", "danger", "info"]


@dataclass
class RunLogMessage:
    """A single log message with optional timestamp, tone, raw text, and rich segments."""
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


@dataclass
class TaskLogRecord:
    """Structured record for a single MAA task lifecycle: status, timing, messages, raw lines."""
    name: str
    status: TaskStatus
    task_id: str | None = None
    source_name: str | None = None
    rule_id: str = "maa-task-lifecycle"
    panel_kind: str = "task"
    started_at: str | None = None
    ended_at: str | None = None
    messages: list[RunLogMessage] = field(default_factory=list)
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
class SummaryLogRecord:
    """Structured record for run summary panel: status, messages, raw lines."""
    status: TaskStatus = "succeeded"
    title: str = "运行摘要"
    messages: list[RunLogMessage] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "summary",
            "title": self.title,
            "status": self.status,
            "messages": [message.to_dict() for message in self.messages],
            "lines": list(self.lines),
        }


LogEntry = RunLogMessage | SummaryLogRecord | TaskLogRecord
