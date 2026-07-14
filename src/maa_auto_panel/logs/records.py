from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from maa_auto_panel.time_utils import server_now_iso


BlockStatus = Literal["default", "running", "succeeded", "failed", "stopped", "unknown", "unfinished", "warning"]
LogTone = Literal["default", "success", "warning", "danger", "info", "theme"]


@dataclass
class LogMessage:
    """A rendered message inside a visible log block."""

    text: str
    time: str | None = None
    tone: LogTone = "default"
    raw: str | None = None
    segments: list[dict[str, object]] = field(default_factory=list)
    image: dict[str, object] | None = None
    indent: int = 0
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
        if self.indent:
            data["indent"] = self.indent
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass
class LogEntry:
    """A single visible log block. All panel rows use this shape."""

    id: str
    source: str
    kind: str
    title: str = ""
    status: BlockStatus | None = None
    time: str | None = None
    opened_at: str | None = None
    sealed_at: str | None = None
    updated_at: str | None = None
    closed: bool = True
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

    def touch(self) -> None:
        self.updated_at = server_now_iso()

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "type": "block",
            "id": self.id,
            "source": self.source,
            "kind": self.kind,
            "updated_at": self.updated_at or server_now_iso(),
            "closed": self.closed,
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
        if self.opened_at:
            data["opened_at"] = self.opened_at
        if self.sealed_at:
            data["sealed_at"] = self.sealed_at
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
