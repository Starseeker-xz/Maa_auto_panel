from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from maa_auto_panel.logs.pipeline import LogPipelineSession, LogSourceSpec, framework_event_translate_line


@dataclass
class RunLogBuffer:
    """Bounded visible-log buffer backed by a source-template pipeline."""

    max_output_chunks: int = 2000
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
            "log_entries": self.entries(),
        }

    def append(self, text: str, *, source: str = "output", metadata: dict[str, object] | None = None) -> bool:
        before = self.pipeline.state_generation
        rendered = self.pipeline.append(text, source=source, metadata=metadata)
        changed = bool(rendered) or self.pipeline.state_generation != before
        if rendered:
            self.output.append(rendered)
        return changed

    def flush(self) -> bool:
        before = self.pipeline.state_generation
        rendered = self.pipeline.flush()
        changed = bool(rendered) or self.pipeline.state_generation != before
        if rendered:
            self.output.append(rendered)
        return changed

    def entries(self) -> list[dict[str, object]]:
        return self.pipeline.entries()

    def begin_task_sequence(self, tasks: list[dict[str, str]]) -> None:
        self.pipeline.begin_task_sequence(tasks)

    def current_block_elapsed_seconds(self, *, kind: str | None = None) -> tuple[str, float] | None:
        return self.pipeline.current_block_elapsed_seconds(kind=kind)
