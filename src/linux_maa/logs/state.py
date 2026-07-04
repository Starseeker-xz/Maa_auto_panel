from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from linux_maa.logs.pipeline import LogPipelineSession, LogSourceSpec, framework_event_translate_line
from linux_maa.logs.records import LogEntry


@dataclass
class RunLogBuffer:
    """Bounded visible-log buffer backed by a source-template pipeline."""

    max_output_chunks: int = 2000
    max_task_records: int = 500
    pipeline: LogPipelineSession = field(default_factory=LogPipelineSession)
    output: deque[str] = field(init=False)

    def __post_init__(self) -> None:
        self.output = deque(maxlen=self.max_output_chunks)
        self.register_source(LogSourceSpec("framework:event", default_tone="info", default_translate_line=framework_event_translate_line))

    def register_source(self, spec: LogSourceSpec) -> None:
        self.pipeline.register_source(spec)

    def to_dict(self) -> dict[str, object]:
        return {
            "output": list(self.output),
            "task_results": self.task_results(),
            "log_entries": self.entries(),
        }

    def append(self, text: str, *, source: str = "output", metadata: dict[str, object] | None = None) -> bool:
        rendered = self.pipeline.append(text, source=source, metadata=metadata)
        if not rendered:
            return False
        self.output.append(rendered)
        return True

    def flush(self) -> bool:
        rendered = self.pipeline.flush()
        if not rendered:
            return False
        self.output.append(rendered)
        return True

    def task_results(self) -> list[dict[str, object]]:
        return [_task_entry_to_result(record) for record in self.pipeline.projected_entries("task")][-self.max_task_records :]

    def entries(self) -> list[dict[str, object]]:
        return self.pipeline.entries()

    def begin_task_sequence(self, tasks: list[dict[str, str]]) -> None:
        self.pipeline.begin_task_sequence(tasks)

    def current_block_elapsed_seconds(self, *, kind: str | None = None) -> tuple[str, float] | None:
        return self.pipeline.current_block_elapsed_seconds(kind=kind)


def _task_entry_to_result(record: LogEntry) -> dict[str, object]:
    status = record.status if record.status and record.status != "default" else "unknown"
    return {
        key: value
        for key, value in {
            "type": "task",
            "name": record.name or record.title,
            "task_id": record.task_id,
            "source_name": record.source_name,
            "status": status,
            "rule_id": record.rule_id,
            "panel_kind": record.panel_kind,
            "started_at": record.started_at,
            "ended_at": record.ended_at,
            "messages": [message.to_dict() for message in record.messages],
            "lines": list(record.lines),
        }.items()
        if value is not None
    }
