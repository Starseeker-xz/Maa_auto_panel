from __future__ import annotations

import re
from dataclasses import dataclass, field

from maa_auto_panel.time_utils import server_datetime_from_text


LOG_LINE_RE = re.compile(
    r"^\[(?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>[A-Z]+)\s*\]\s*(?P<body>.*)$"
)
TASK_EVENT_RE = re.compile(r"^(?P<task>[A-Za-z][A-Za-z0-9_]*?)\s+(?P<event>Start|Completed|Error|Stopped)\s*$")


@dataclass(frozen=True)
class MaaTaskDescriptor:
    task_id: str
    source_name: str
    name: str


@dataclass
class MaaTaskResultCollector:
    """Collect authoritative Maa task results from raw maa-cli stderr lines."""

    expected_tasks: list[MaaTaskDescriptor]
    expected_index: int = 0
    results: list[dict[str, object]] = field(default_factory=list)
    _active_by_source: dict[str, dict[str, object]] = field(default_factory=dict)

    def consume_raw_line(self, source: str, line: str) -> None:
        if source != "maa-cli:stderr":
            return
        parsed = parse_log_line(line)
        body = str(parsed["body"] or "")
        if body == "Error: Interrupted by user!":
            for result in list(self._active_by_source.values()):
                result["status"] = "unfinished"
                result["ended_at"] = parsed["time"]
                result.setdefault("lines", []).append(line)
            self._active_by_source.clear()
            return

        match = TASK_EVENT_RE.match(body)
        if match is None:
            return
        source_name = match.group("task")
        status = task_status(match.group("event"))
        if status is None:
            return
        if status == "running":
            self._start_task(source_name, parsed["time"], line)
            return
        self._finish_task(source_name, status, parsed["time"], line)

    def finish(self) -> None:
        for result in list(self._active_by_source.values()):
            if result.get("status") == "running":
                result["status"] = "unfinished"
        self._active_by_source.clear()

    def status_by_task_id(self, task_ids: list[str]) -> dict[str, str]:
        by_id = {str(result.get("task_id") or ""): str(result.get("status") or "unknown") for result in self.results}
        return {task_id: by_id.get(task_id, "missing") for task_id in task_ids}

    def _start_task(self, source_name: str, time_text: str | None, line: str) -> None:
        descriptor = self._next_expected_task(source_name)
        result: dict[str, object] = {
            "type": "task",
            "name": descriptor.name,
            "task_id": descriptor.task_id,
            "source_name": source_name,
            "status": "running",
            "started_at": time_text,
            "lines": [line],
        }
        self.results.append(result)
        self._active_by_source[source_name] = result

    def _finish_task(self, source_name: str, status: str, time_text: str | None, line: str) -> None:
        result = self._active_by_source.pop(source_name, None)
        if result is None:
            descriptor = self._next_expected_task(source_name)
            result = {
                "type": "task",
                "name": descriptor.name,
                "task_id": descriptor.task_id,
                "source_name": source_name,
                "lines": [],
            }
            self.results.append(result)
        result["status"] = status
        result["ended_at"] = time_text
        result.setdefault("lines", []).append(line)

    def _next_expected_task(self, source_name: str) -> MaaTaskDescriptor:
        for index in range(self.expected_index, len(self.expected_tasks)):
            task = self.expected_tasks[index]
            if task.source_name != source_name:
                continue
            self.expected_index = index + 1
            return task
        return MaaTaskDescriptor(task_id="", source_name=source_name, name=source_name)


def parse_log_line(raw: str) -> dict[str, str | None]:
    match = LOG_LINE_RE.match(raw)
    if match is None:
        return {"time": None, "level": None, "body": raw}
    return {
        "time": server_datetime_from_text(match.group("time")),
        "level": match.group("level"),
        "body": match.group("body"),
    }


def task_status(event: str) -> str | None:
    if event == "Start":
        return "running"
    if event == "Completed":
        return "succeeded"
    if event == "Error":
        return "failed"
    if event == "Stopped":
        return "stopped"
    return None
