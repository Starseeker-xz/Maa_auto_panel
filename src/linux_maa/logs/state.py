from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from linux_maa.logs.pipeline import LogPipelineSession, LogSourceSpec
from linux_maa.logs.records import LogTone


@dataclass
class RunLogBuffer:
    """Bounded visible-log buffer backed by a source-template pipeline."""

    max_output_chunks: int = 2000
    max_task_records: int = 500
    pipeline: LogPipelineSession = field(default_factory=LogPipelineSession)
    output: deque[str] = field(init=False)

    def __post_init__(self) -> None:
        self.output = deque(maxlen=self.max_output_chunks)

    def register_source(self, spec: LogSourceSpec) -> None:
        self.pipeline.register_source(spec)

    def to_dict(self) -> dict[str, object]:
        return {
            "output": list(self.output),
            "task_results": self.task_results(),
            "log_entries": self.entries(),
        }

    def append(self, text: str, *, source: str = "output") -> bool:
        rendered = self.pipeline.append(text, source=source)
        if not rendered:
            return False
        self.output.append(rendered)
        return True

    def append_event(self, text: str, *, source: str = "framework:event", time: str | None = None, tone: LogTone = "info") -> bool:
        rendered = self.pipeline.append_event(text, source=source, time=time, tone=tone)
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
        results: list[dict[str, object]] = []
        seen_templates: set[int] = set()
        for spec in self.pipeline.sources.values():
            template_id = id(spec.template)
            if template_id in seen_templates:
                continue
            seen_templates.add(template_id)
            getter = getattr(spec.template, "task_results", None)
            if callable(getter):
                results.extend(getter(max_items=self.max_task_records))
        return results[-self.max_task_records :]

    def entries(self) -> list[dict[str, object]]:
        return self.pipeline.entries()

    def begin_task_sequence(self, tasks: list[dict[str, str]]) -> None:
        for spec in self.pipeline.sources.values():
            begin = getattr(spec.template, "begin_task_sequence", None)
            if callable(begin):
                begin(tasks)

    def current_block_elapsed_seconds(self, *, kind: str | None = None) -> tuple[str, float] | None:
        candidates: list[tuple[str, float]] = []
        seen_templates: set[int] = set()
        for spec in self.pipeline.sources.values():
            template_id = id(spec.template)
            if template_id in seen_templates:
                continue
            seen_templates.add(template_id)
            getter = getattr(spec.template, "current_block_elapsed_seconds", None)
            if callable(getter):
                current = getter(kind=kind)
                if current is not None:
                    candidates.append(current)
                continue
        return max(candidates, key=lambda item: item[1]) if candidates else None
