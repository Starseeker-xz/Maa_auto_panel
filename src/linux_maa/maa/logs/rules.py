from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from linux_maa.maa.logs.records import TaskStatus


ParsedLine = dict[str, str | None]
RuleKind = Literal["line", "summary", "task"]


LOG_LINE_RE = re.compile(
    r"^\[(?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>[A-Z]+)\s*\]\s*(?P<body>.*)$"
)
TASK_EVENT_RE = re.compile(
    r"^(?P<task>[A-Za-z][A-Za-z0-9_]*?)\s+"
    r"(?P<event>Start|Completed|Error|Stopped)\s*$"
)


@dataclass(frozen=True)
class LogRuleMatch:
    kind: RuleKind
    rule_id: str
    panel_kind: str
    name: str = ""
    event: str = ""
    status: TaskStatus | None = None


@dataclass(frozen=True)
class LogRule:
    id: str
    kind: RuleKind
    panel_kind: str

    def match(self, parsed: ParsedLine) -> LogRuleMatch | None:
        raise NotImplementedError


@dataclass(frozen=True)
class SummaryLogRule(LogRule):
    marker: str = "Summary"

    def match(self, parsed: ParsedLine) -> LogRuleMatch | None:
        if parsed["body"] != self.marker:
            return None
        return LogRuleMatch(kind=self.kind, rule_id=self.id, panel_kind=self.panel_kind)


@dataclass(frozen=True)
class TaskLifecycleLogRule(LogRule):
    event_pattern: re.Pattern[str] = TASK_EVENT_RE
    start_events: frozenset[str] = frozenset({"Start"})
    end_status_by_event: dict[str, TaskStatus] | None = None
    name_group: str = "task"
    event_group: str = "event"

    def match(self, parsed: ParsedLine) -> LogRuleMatch | None:
        body = str(parsed["body"] or "")
        match = self.event_pattern.match(body)
        if match is None:
            return None

        name = match.group(self.name_group)
        event = match.group(self.event_group)
        if event in self.start_events:
            return LogRuleMatch(
                kind=self.kind,
                rule_id=self.id,
                panel_kind=self.panel_kind,
                name=name,
                event=event,
                status="running",
            )

        status_by_event = self.end_status_by_event or {}
        status = status_by_event.get(event)
        if status is None:
            return None
        return LogRuleMatch(
            kind=self.kind,
            rule_id=self.id,
            panel_kind=self.panel_kind,
            name=name,
            event=event,
            status=status,
        )


@dataclass(frozen=True)
class DefaultLineLogRule(LogRule):
    def match(self, parsed: ParsedLine) -> LogRuleMatch:
        return LogRuleMatch(kind=self.kind, rule_id=self.id, panel_kind=self.panel_kind)


DEFAULT_PANEL_RULES: tuple[LogRule, ...] = (
    SummaryLogRule(id="maa-summary", kind="summary", panel_kind="summary"),
    TaskLifecycleLogRule(
        id="maa-task-lifecycle",
        kind="task",
        panel_kind="task",
        end_status_by_event={
            "Completed": "succeeded",
            "Error": "failed",
            "Stopped": "stopped",
        },
    ),
    DefaultLineLogRule(id="default-line", kind="line", panel_kind="line"),
)


def parse_log_line(raw: str) -> ParsedLine:
    match = LOG_LINE_RE.match(raw)
    if match is None:
        return {"time": None, "level": None, "body": raw}
    return {
        "time": match.group("time")[-8:],
        "level": match.group("level"),
        "body": match.group("body"),
    }


def match_log_rule(parsed: ParsedLine, rules: tuple[LogRule, ...] = DEFAULT_PANEL_RULES) -> LogRuleMatch:
    for rule in rules:
        matched = rule.match(parsed)
        if matched is not None:
            return matched
    return LogRuleMatch(kind="line", rule_id="default-line", panel_kind="line")
