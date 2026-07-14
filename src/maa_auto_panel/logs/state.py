from __future__ import annotations

from dataclasses import dataclass, field

from maa_auto_panel.logs.pipeline import LogPipelineSession, LogSourceSpec, framework_event_translate_line


@dataclass
class RunLogBuffer:
    """Bounded visible-log buffer backed by a source-template pipeline."""

    pipeline: LogPipelineSession = field(default_factory=LogPipelineSession)

    def __post_init__(self) -> None:
        self.register_source(LogSourceSpec("framework:event", default_tone="info", default_translate_line=framework_event_translate_line))

    def register_source(self, spec: LogSourceSpec) -> None:
        self.pipeline.register_source(spec)

    def append(self, text: str, *, source: str = "output", metadata: dict[str, object] | None = None) -> bool:
        return self.pipeline.append(text, source=source, metadata=metadata)

    def flush(self) -> bool:
        return self.pipeline.flush()

    def entries(self) -> list[dict[str, object]]:
        return self.pipeline.entries()

    def current_block_elapsed_seconds(self, *, kind: str | None = None) -> tuple[str, float] | None:
        return self.pipeline.current_block_elapsed_seconds(kind=kind)
