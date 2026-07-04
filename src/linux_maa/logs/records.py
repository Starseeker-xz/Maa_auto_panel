from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


TaskStatus = Literal["running", "succeeded", "failed", "stopped", "unknown"]
LogTone = Literal["default", "success", "warning", "danger", "info"]
LogBlockKind = Literal["line", "task", "summary", "event"]


@dataclass
class LogMessage:
    """A rendered message inside a visible log block."""

    text: str
    time: str | None = None
    tone: LogTone = "default"
    raw: str | None = None
    segments: list[dict[str, object]] = field(default_factory=list)
    image: dict[str, object] | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "text": self.text,
            "tone": self.tone,
        }
        if self.time:
            data["time"] = self.time
        if self.raw:
            data["raw"] = self.raw
        if self.segments:
            data["segments"] = list(self.segments)
        if self.image:
            data["image"] = dict(self.image)
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass
class LogEntry:
    """A single visible log block. All panel rows use this shape."""

    id: str
    source: str
    kind: LogBlockKind
    title: str = ""
    status: TaskStatus | None = None
    time: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    tone: LogTone = "default"
    messages: list[LogMessage] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    raw: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    name: str | None = None
    task_id: str | None = None
    source_name: str | None = None
    rule_id: str | None = None
    panel_kind: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "type": "block",
            "id": self.id,
            "source": self.source,
            "kind": self.kind,
            "tone": self.tone,
            "messages": [message.to_dict() for message in self.messages],
            "lines": list(self.lines),
        }
        if self.title:
            data["title"] = self.title
        if self.status:
            data["status"] = self.status
        if self.time:
            data["time"] = self.time
        if self.started_at:
            data["started_at"] = self.started_at
        if self.ended_at:
            data["ended_at"] = self.ended_at
        if self.raw:
            data["raw"] = self.raw
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        if self.name:
            data["name"] = self.name
        if self.task_id:
            data["task_id"] = self.task_id
        if self.source_name and self.source_name != self.name:
            data["source_name"] = self.source_name
        if self.rule_id:
            data["rule_id"] = self.rule_id
        if self.panel_kind:
            data["panel_kind"] = self.panel_kind
        return data
