from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Protocol

from linux_maa.logs.records import LogEntry, LogMessage, LogTone, TaskStatus


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class LogTemplate(Protocol):
    """Source-specific visible-log template."""

    def handle_line(self, session: "LogPipelineSession", source: str, raw: str) -> str:
        ...

    def flush_source(self, session: "LogPipelineSession", source: str) -> str:
        ...


@dataclass(frozen=True)
class LogSourceSpec:
    source_id: str
    template: LogTemplate
    default_tone: LogTone = "default"


@dataclass
class PlainLogTemplate:
    """Template that turns every line into an independent block."""

    kind: str = "line"

    def handle_line(self, session: "LogPipelineSession", source: str, raw: str) -> str:
        spec = session.source_spec(source)
        text = terminal_display_text(raw)
        if not text:
            return ""
        message = LogMessage(text=text, tone=spec.default_tone, raw=raw if raw != text else None)
        session.append_block(
            source,
            kind=self.kind,
            title=text if self.kind != "line" else "",
            tone=spec.default_tone,
            messages=[message],
            lines=[raw],
            raw=raw,
        )
        return f"{text}\n"

    def flush_source(self, session: "LogPipelineSession", source: str) -> str:
        return ""


@dataclass
class EventLogTemplate:
    """Template for framework events flowing through the same block model."""

    def handle_line(self, session: "LogPipelineSession", source: str, raw: str) -> str:
        spec = session.source_spec(source)
        text = terminal_display_text(raw)
        if not text:
            return ""
        time_text = session.event_time
        message = LogMessage(text=text, time=time_text, tone=spec.default_tone)
        session.append_block(
            source,
            kind="event",
            title=text,
            time=time_text,
            tone=spec.default_tone,
            messages=[message],
            lines=[raw],
            raw=raw,
        )
        return f"{format_time_prefix(time_text)}{text}\n"

    def flush_source(self, session: "LogPipelineSession", source: str) -> str:
        return ""


@dataclass
class _SourceState:
    partial: str = ""
    terminal_entry: LogEntry | None = None
    terminal_last_emit: float = 0.0
    terminal_last_output: str = ""


@dataclass
class LogPipelineSession:
    """Generic visible-log pipeline shared by manual runs, scheduler, tools, and maintenance."""

    max_log_entries: int = 1000
    max_record_messages: int = 300
    max_record_lines: int = 300
    terminal_update_interval_seconds: float = 2.0
    entries_list: list[LogEntry] = field(default_factory=list)
    sources: dict[str, LogSourceSpec] = field(default_factory=dict)
    _source_states: dict[str, _SourceState] = field(default_factory=dict)
    _next_entry_id: int = 1
    event_time: str | None = None

    def register_source(self, spec: LogSourceSpec) -> None:
        self.sources[normalize_source(spec.source_id)] = LogSourceSpec(
            source_id=normalize_source(spec.source_id),
            template=spec.template,
            default_tone=spec.default_tone,
        )

    def source_spec(self, source: str) -> LogSourceSpec:
        source_key = normalize_source(source)
        spec = self.sources.get(source_key)
        if spec is None:
            spec = LogSourceSpec(source_key, PlainLogTemplate(), default_tone_for_source(source_key))
            self.sources[source_key] = spec
        return spec

    def append(self, text: str, *, source: str = "output") -> str:
        if not text:
            return ""
        source_key = normalize_source(source)
        self.source_spec(source_key)
        state = self._state(source_key)
        text = state.partial + text
        state.partial = ""
        return self._append_text(text, source_key)

    def append_event(self, text: str, *, source: str = "framework:event", time: str | None = None, tone: LogTone = "info") -> str:
        source_key = normalize_source(source)
        self.register_source(LogSourceSpec(source_key, EventLogTemplate(), tone))
        previous_time = self.event_time
        self.event_time = time
        try:
            rendered = self.append(_ensure_newline(text), source=source_key)
        finally:
            self.event_time = previous_time
        return rendered

    def flush(self, *, source: str | None = None) -> str:
        output = ""
        sources = [normalize_source(source)] if source is not None else self._active_sources()
        for source_key in sources:
            state = self._state(source_key)
            if state.partial:
                if state.terminal_entry is not None:
                    output += self._handle_terminal_update(state.partial, source_key, final=True)
                else:
                    output += self.source_spec(source_key).template.handle_line(self, source_key, state.partial)
                state.partial = ""
            if state.terminal_entry is not None:
                output += self._finalize_terminal_update(source_key)
            output += self.source_spec(source_key).template.flush_source(self, source_key)
        return output

    def append_block(
        self,
        source: str,
        *,
        kind: str,
        title: str = "",
        status: TaskStatus | None = None,
        time: str | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        tone: LogTone = "default",
        messages: list[LogMessage] | None = None,
        lines: list[str] | None = None,
        raw: str | None = None,
        metadata: dict[str, object] | None = None,
        name: str | None = None,
        task_id: str | None = None,
        source_name: str | None = None,
        rule_id: str | None = None,
        panel_kind: str | None = None,
    ) -> LogEntry:
        entry = LogEntry(
            id=self._new_entry_id(),
            source=normalize_source(source),
            kind=kind,  # type: ignore[arg-type]
            title=title,
            status=status,
            time=time,
            started_at=started_at,
            ended_at=ended_at,
            tone=tone,
            messages=messages or [],
            lines=lines or [],
            raw=raw,
            metadata=metadata or {},
            name=name,
            task_id=task_id,
            source_name=source_name,
            rule_id=rule_id,
            panel_kind=panel_kind,
        )
        self.entries_list.append(entry)
        self._trim()
        return entry

    def entries(self) -> list[dict[str, object]]:
        return [entry.to_dict() for entry in self.entries_list]

    def _append_text(self, text: str, source: str) -> str:
        output = ""
        line = ""
        index = 0
        while index < len(text):
            char = text[index]
            if char == "\r":
                if index + 1 < len(text) and text[index + 1] == "\n":
                    output += self.source_spec(source).template.handle_line(self, source, line)
                    line = ""
                    index += 2
                    continue
                output += self._handle_terminal_update(line, source)
                line = ""
            elif char == "\n":
                state = self._state(source)
                if state.terminal_entry is not None:
                    if line:
                        output += self._handle_terminal_update(line, source, final=True)
                    output += self._finalize_terminal_update(source)
                else:
                    output += self.source_spec(source).template.handle_line(self, source, line)
                line = ""
            elif char in {"\b", "\x7f"}:
                line = line[:-1]
            else:
                line += char
            index += 1

        if line:
            self._state(source).partial = line
        return output

    def _handle_terminal_update(self, raw: str, source: str, *, final: bool = False) -> str:
        text = terminal_display_text(raw)
        if not text:
            return ""

        state = self._state(source)
        message = LogMessage(text=text, tone="info", raw=text)
        first_update = state.terminal_entry is None
        if state.terminal_entry is None:
            state.terminal_entry = self.append_block(
                source,
                kind="line",
                tone="info",
                messages=[message],
                lines=[text],
                raw=text,
            )
        else:
            state.terminal_entry.messages = [message]
            state.terminal_entry.lines = [text]
            state.terminal_entry.raw = text

        now = time.monotonic()
        should_emit = first_update or final or now - state.terminal_last_emit >= self.terminal_update_interval_seconds
        if should_emit:
            state.terminal_last_emit = now
            state.terminal_last_output = text
            return f"{text}\n"
        return ""

    def _finalize_terminal_update(self, source: str) -> str:
        state = self._state(source)
        entry = state.terminal_entry
        last_output = state.terminal_last_output
        state.terminal_entry = None
        state.terminal_last_emit = 0.0
        state.terminal_last_output = ""
        if entry is None:
            return ""
        text = entry.messages[0].text if entry.messages else ""
        return f"{text}\n" if text and text != last_output else ""

    def _state(self, source: str) -> _SourceState:
        return self._source_states.setdefault(normalize_source(source), _SourceState())

    def _active_sources(self) -> list[str]:
        keys = set(self.sources)
        keys.update(self._source_states)
        return list(keys)

    def _new_entry_id(self) -> str:
        entry_id = f"log-{self._next_entry_id}"
        self._next_entry_id += 1
        return entry_id

    def _trim(self) -> None:
        _trim_list(self.entries_list, self.max_log_entries)
        for entry in self.entries_list:
            _trim_list(entry.messages, self.max_record_messages)
            _trim_list(entry.lines, self.max_record_lines)


def normalize_source(source: str | None) -> str:
    if source is None:
        return "stdout"
    text = str(source)
    if text in {"", "output", "stdout"}:
        return "stdout"
    if text == "stderr":
        return "stderr"
    return text


def default_tone_for_source(source: str) -> LogTone:
    return "warning" if source == "stderr" or source.endswith(":stderr") else "default"


def format_time_prefix(time_text: str | None) -> str:
    return f"{time_text} " if time_text else ""


def terminal_display_text(raw: str) -> str:
    return ANSI_ESCAPE_RE.sub("", raw).strip()


def _trim_list(values: list[object], max_items: int) -> None:
    if max_items < 0:
        return
    overflow = len(values) - max_items
    if overflow > 0:
        del values[:overflow]


def _ensure_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"
