from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from maa_auto_panel.logs.pipeline import LogSourceSpec, default_tone_for_source, plain_translate_line
from maa_auto_panel.logs.state import RunLogBuffer


StreamSourceMapper = Callable[[str], str]
DiagnosticSink = Callable[[str, str, str], None]
SourceRegistrar = Callable[[RunLogBuffer], None]


def default_stream_source(stream: str) -> str:
    return f"process:{stream}"


@dataclass(frozen=True)
class RunLogProfile:
    """Connects process streams to visible-log sources and optional diagnostic sinks."""

    max_output_chunks: int = 2000
    register_sources: SourceRegistrar | None = None
    source_for_stream: StreamSourceMapper = default_stream_source
    diagnostic_sink: DiagnosticSink | None = None

    def new_buffer(self) -> RunLogBuffer:
        log = RunLogBuffer(max_output_chunks=self.max_output_chunks)
        if self.register_sources is not None:
            self.register_sources(log)
        return log

    def visible_source(self, stream: str) -> str:
        return self.source_for_stream(stream)

    def append_diagnostics(self, run_id: str, stream: str, text: str) -> None:
        if self.diagnostic_sink is not None:
            self.diagnostic_sink(run_id, stream, text)


def plain_stream_log_profile(
    prefix: str,
    *,
    max_output_chunks: int = 2000,
    diagnostic_sink: DiagnosticSink | None = None,
) -> RunLogProfile:
    def register(log: RunLogBuffer) -> None:
        for source in (f"{prefix}:stdout", f"{prefix}:stderr"):
            log.register_source(LogSourceSpec(source, default_tone_for_source(source), plain_translate_line))

    return RunLogProfile(
        max_output_chunks=max_output_chunks,
        register_sources=register,
        source_for_stream=lambda stream: f"{prefix}:{stream}",
        diagnostic_sink=diagnostic_sink,
    )
