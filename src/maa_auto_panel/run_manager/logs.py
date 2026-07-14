from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from maa_auto_panel.logs.pipeline import LogSourceSpec, default_tone_for_source, plain_translate_line
from maa_auto_panel.logs.state import RunLogBuffer


StreamSourceMapper = Callable[[str], str]
DiagnosticSink = Callable[[str, str, str], None]
BufferConfigurator = Callable[[RunLogBuffer], None]


def default_stream_source(stream: str) -> str:
    return f"process:{stream}"


@dataclass(frozen=True)
class RunLogProfile:
    """Connects process streams to visible-log sources and optional diagnostic sinks."""

    source_specs: tuple[LogSourceSpec, ...] = ()
    configure_buffer: BufferConfigurator | None = None
    source_for_stream: StreamSourceMapper = default_stream_source
    diagnostic_sink: DiagnosticSink | None = None

    def new_buffer(self) -> RunLogBuffer:
        log = RunLogBuffer()
        for source_spec in self.source_specs:
            log.register_source(source_spec)
        if self.configure_buffer is not None:
            self.configure_buffer(log)
        return log

    def visible_source(self, stream: str) -> str:
        return self.source_for_stream(stream)

    def append_diagnostics(self, run_id: str, stream: str, text: str) -> None:
        if self.diagnostic_sink is not None:
            self.diagnostic_sink(run_id, stream, text)


def plain_stream_log_profile(
    prefix: str,
    *,
    diagnostic_sink: DiagnosticSink | None = None,
) -> RunLogProfile:
    sources = tuple(
        LogSourceSpec(source, default_tone_for_source(source), plain_translate_line)
        for source in (f"{prefix}:stdout", f"{prefix}:stderr")
    )
    return RunLogProfile(
        source_specs=sources,
        source_for_stream=lambda stream: f"{prefix}:{stream}",
        diagnostic_sink=diagnostic_sink,
    )
