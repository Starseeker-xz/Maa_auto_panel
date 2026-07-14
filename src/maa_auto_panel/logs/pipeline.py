from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Literal

from maa_auto_panel.logs.records import BlockStatus, LogEntry, LogMessage, LogTone
from maa_auto_panel.time_utils import server_now_iso


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

CloseReason = Literal["matched_end", "superseded", "passive_boundary", "flush"]


@dataclass(frozen=True)
class LogLineInput:
    """A normalized single-line input flowing through the block pipeline."""

    raw: str
    source: str
    metadata: dict[str, object]
    default_tone: LogTone = "default"
    processed: str | None = None

    @property
    def content(self) -> str:
        return self.raw if self.processed is None else self.processed

    @property
    def text(self) -> str:
        return terminal_display_text(self.content)

    @property
    def time(self) -> str | None:
        return _metadata_str(self.metadata, "time")

    @property
    def tone(self) -> LogTone:
        return _tone_from_metadata(self.metadata, self.default_tone)


@dataclass
class LogLineTranslation:
    """Rendered representation for a fallback one-line block."""

    text: str = ""
    kind: str = "line"
    title: str = ""
    status: BlockStatus | None = "default"
    time: str | None = None
    opened_at: str | None = None
    sealed_at: str | None = None
    tone: LogTone = "default"
    messages: list[LogMessage] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    raw: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


LinePreprocessor = Callable[[str, dict[str, object]], tuple[str, dict[str, object]]]
DefaultTranslateLine = Callable[[LogLineInput, "LogPipelineSession"], LogLineTranslation | None]


@dataclass(frozen=True)
class LogSourceSpec:
    source_id: str
    default_tone: LogTone = "default"
    default_translate_line: DefaultTranslateLine | None = None
    preprocess_line: LinePreprocessor | None = None


@dataclass
class BlockStartOutcome:
    keep_active: bool = True


@dataclass
class ActiveBlock:
    source: str
    definition: "BlockDefinition"
    entry: LogEntry
    context: dict[str, object] = field(default_factory=dict)
    locked_fields: set[str] = field(default_factory=set)

    def update_entry(self, *, lock: bool = False, **fields: object) -> None:
        for key, value in fields.items():
            if key in self.locked_fields and not lock:
                continue
            setattr(self.entry, key, value)
            if lock:
                self.locked_fields.add(key)
        self.entry.touch()


@dataclass(frozen=True)
class BlockStartContext:
    session: "LogPipelineSession"
    previous_block: ActiveBlock | None = None

    def update_previous_entry(self, **fields: object) -> None:
        if self.previous_block is not None:
            self.previous_block.update_entry(**fields)


StartMatcher = Callable[[LogLineInput, "LogPipelineSession"], object | None]
EndMatcher = Callable[[ActiveBlock, LogLineInput, "LogPipelineSession"], object | None]
LineTranslator = Callable[[ActiveBlock, LogLineInput, "LogPipelineSession"], None]
BlockStartHook = Callable[[ActiveBlock, LogLineInput, object, BlockStartContext], BlockStartOutcome | None]
BlockCloseHook = Callable[[ActiveBlock, CloseReason, LogLineInput | None, object | None, "LogPipelineSession"], None]
SourcePredicate = Callable[[str], bool]


@dataclass(frozen=True)
class BlockDefinition:
    """A source-scoped streaming block rule."""

    kind: str
    source_predicate: SourcePredicate
    start_matcher: StartMatcher
    translate_line: LineTranslator
    end_matcher: EndMatcher | None = None
    passive_boundary_matcher: EndMatcher | None = None
    on_start: BlockStartHook | None = None
    on_close: BlockCloseHook | None = None
    default_title: str = ""
    default_status: BlockStatus | None = "default"
    default_tone: LogTone = "default"
    rule_id: str | None = None
    panel_kind: str | None = None


@dataclass
class _SourceState:
    partial: str = ""
    partial_metadata: dict[str, object] = field(default_factory=dict)
    terminal_entry: LogEntry | None = None
    preprocessor_state: dict[str, object] = field(default_factory=dict)


@dataclass
class LogPipelineSession:
    """Generic visible-log pipeline shared by manual runs, scheduler, tools, and maintenance."""

    max_log_entries: int = 1000
    max_record_messages: int = 300
    max_record_lines: int = 300
    entries_list: list[LogEntry] = field(default_factory=list)
    sources: dict[str, LogSourceSpec] = field(default_factory=dict)
    block_definitions: list[BlockDefinition] = field(default_factory=list)
    active_blocks: dict[str, ActiveBlock] = field(default_factory=dict)
    context: dict[str, object] = field(default_factory=dict)
    state_generation: int = 0
    _source_states: dict[str, _SourceState] = field(default_factory=dict)
    _next_entry_id: int = 1

    def register_source(self, spec: LogSourceSpec) -> None:
        source_key = normalize_source(spec.source_id)
        self.sources[source_key] = LogSourceSpec(
            source_id=source_key,
            default_tone=spec.default_tone,
            default_translate_line=spec.default_translate_line or plain_translate_line,
            preprocess_line=spec.preprocess_line,
        )

    def register_block(self, definition: BlockDefinition) -> None:
        self.block_definitions.append(definition)

    def source_spec(self, source: str) -> LogSourceSpec:
        source_key = normalize_source(source)
        spec = self.sources.get(source_key)
        if spec is None:
            spec = LogSourceSpec(
                source_id=source_key,
                default_tone=default_tone_for_source(source_key),
                default_translate_line=plain_translate_line,
            )
            self.sources[source_key] = spec
        return spec

    def append(self, text: str, *, source: str = "output", metadata: dict[str, object] | None = None) -> bool:
        if not text:
            return False
        before = self.state_generation
        source_key = normalize_source(source)
        self.source_spec(source_key)
        state = self._state(source_key)
        incoming_metadata = dict(metadata or {})
        line_metadata = incoming_metadata
        if state.partial:
            text = state.partial + text
            line_metadata = state.partial_metadata or incoming_metadata
            state.partial = ""
            state.partial_metadata = {}
        self._append_text(text, source_key, line_metadata)
        return self.state_generation != before

    def flush(self, *, source: str | None = None) -> bool:
        before = self.state_generation
        sources = [normalize_source(source)] if source is not None else self._active_sources()
        for source_key in sources:
            state = self._state(source_key)
            if state.partial:
                if state.terminal_entry is not None:
                    self._handle_terminal_update(state.partial, source_key, state.partial_metadata)
                else:
                    self._handle_line(source_key, state.partial, state.partial_metadata)
                state.partial = ""
                state.partial_metadata = {}
            if state.terminal_entry is not None:
                self._finalize_terminal_update(source_key)
            self._close_active(source_key, reason="flush")
        return self.state_generation != before

    def append_block(
        self,
        source: str,
        *,
        kind: str,
        title: str = "",
        status: BlockStatus | None = None,
        time: str | None = None,
        opened_at: str | None = None,
        sealed_at: str | None = None,
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
        closed: bool = True,
    ) -> LogEntry:
        entry = LogEntry(
            id=self._new_entry_id(),
            source=normalize_source(source),
            kind=kind,
            title=title,
            status=status,
            time=time,
            opened_at=opened_at,
            sealed_at=sealed_at,
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
            updated_at=current_datetime_text(),
            closed=closed,
        )
        self.entries_list.append(entry)
        self.state_generation += 1
        self._trim()
        return entry

    def append_active_record(
        self,
        active: ActiveBlock,
        *,
        message: LogMessage | None = None,
        line: str | None = None,
    ) -> None:
        """Append bounded block content so translators never manage buffer limits."""
        if line is not None:
            active.entry.lines.append(line)
        if message is not None:
            active.entry.messages.append(message)
        _trim_list(active.entry.messages, self.max_record_messages)
        _trim_list(active.entry.lines, self.max_record_lines)
        active.entry.touch()

    def entries(self) -> list[dict[str, object]]:
        return [entry.to_dict() for entry in self.entries_list]

    def current_block_elapsed_seconds(self, *, kind: str | None = None) -> tuple[str, float] | None:
        candidates: list[tuple[str, float]] = []
        now = time.monotonic()
        for active in self.active_blocks.values():
            entry = active.entry
            if kind is not None and kind not in {entry.kind, entry.panel_kind}:
                continue
            started = active.context.get("started_monotonic", entry.metadata.get("started_monotonic"))
            if not isinstance(started, (int, float)):
                continue
            candidates.append((entry.name or entry.title or entry.kind, now - float(started)))
        return max(candidates, key=lambda item: item[1]) if candidates else None

    def _append_text(self, text: str, source: str, metadata: dict[str, object]) -> None:
        line = ""
        index = 0
        while index < len(text):
            char = text[index]
            if char == "\r":
                if index + 1 < len(text) and text[index + 1] == "\n":
                    self._handle_line(source, line, metadata)
                    line = ""
                    index += 2
                    continue
                self._handle_terminal_update(line, source, metadata)
                line = ""
            elif char == "\n":
                state = self._state(source)
                if state.terminal_entry is not None:
                    if line:
                        self._handle_terminal_update(line, source, metadata)
                    self._finalize_terminal_update(source)
                else:
                    self._handle_line(source, line, metadata)
                line = ""
            elif char in {"\b", "\x7f"}:
                line = line[:-1]
            else:
                line += char
            index += 1

        if line:
            state = self._state(source)
            state.partial = line
            state.partial_metadata = dict(metadata)
    def _handle_line(self, source: str, raw: str, metadata: dict[str, object]) -> None:
        source_key = normalize_source(source)
        spec = self.source_spec(source_key)
        original = raw.rstrip("\r\n")
        processed = original
        processed_metadata: dict[str, object] = {}
        if spec.preprocess_line is not None:
            processed, processed_metadata = spec.preprocess_line(original, self._state(source_key).preprocessor_state)
        processed_metadata.update(metadata)
        if not processed:
            return
        line = LogLineInput(
            raw=original,
            source=source_key,
            metadata=processed_metadata,
            default_tone=spec.default_tone,
            processed=processed,
        )
        active = self.active_blocks.get(source_key)
        if active is not None:
            end_match = _call_matcher(active.definition.end_matcher, active, line, self)
            if _is_match(end_match):
                self._close_active(source_key, reason="matched_end", line=line, match=end_match)
                if not bool(getattr(end_match, "reprocess", False)):
                    return
                active = None

            if active is not None:
                boundary_match = _call_matcher(active.definition.passive_boundary_matcher, active, line, self)
                if _is_match(boundary_match):
                    self._close_active(source_key, reason="passive_boundary", line=line, match=boundary_match)
                    active = None

        start_definition, start_match = self._match_start(line)
        if start_definition is not None:
            previous_block = self.active_blocks.get(source_key)
            if previous_block is not None:
                self._close_active(source_key, reason="superseded", line=line, match=start_match)
            started_block = self._start_block(source_key, start_definition, line)
            outcome = self._run_start_hook(started_block, line, start_match, previous_block)
            self._ensure_block_start_time(started_block.entry)
            if outcome.keep_active:
                self.active_blocks[source_key] = started_block
            else:
                self.active_blocks.pop(source_key, None)
            return

        active = self.active_blocks.get(source_key) if active is None else active
        if active is not None:
            active.definition.translate_line(active, line, self)
            active.entry.touch()
            self.state_generation += 1
            return
        self._append_fallback_line(line)

    def _match_start(self, line: LogLineInput) -> tuple[BlockDefinition | None, object | None]:
        for definition in self.block_definitions:
            if not definition.source_predicate(line.source):
                continue
            match = definition.start_matcher(line, self)
            if _is_match(match):
                return definition, match
        return None, None

    def _start_block(self, source: str, definition: BlockDefinition, line: LogLineInput) -> ActiveBlock:
        entry = self.append_block(
            source,
            kind=definition.kind,
            title=definition.default_title,
            status=definition.default_status,
            time=line.time,
            opened_at=line.time or current_datetime_text(),
            tone=_tone_from_metadata(line.metadata, definition.default_tone),
            lines=[],
            rule_id=definition.rule_id,
            panel_kind=definition.panel_kind,
            closed=False,
        )
        active = ActiveBlock(source=source, definition=definition, entry=entry)
        return active

    def _run_start_hook(self, active: ActiveBlock, line: LogLineInput, match: object | None, previous: ActiveBlock | None) -> BlockStartOutcome:
        if active.definition.on_start is None:
            self.append_active_record(active, line=line.raw)
            return BlockStartOutcome()
        result = active.definition.on_start(active, line, match, BlockStartContext(session=self, previous_block=previous))
        active.entry.touch()
        if result is None:
            return BlockStartOutcome()
        return result

    def _close_active(
        self,
        source: str,
        *,
        reason: CloseReason,
        line: LogLineInput | None = None,
        match: object | None = None,
    ) -> None:
        active = self.active_blocks.pop(normalize_source(source), None)
        if active is None:
            return
        active.entry.closed = True
        if active.entry.sealed_at is None:
            active.entry.sealed_at = line.time if line and line.time else current_datetime_text()
        active.entry.touch()
        self.state_generation += 1
        if active.definition.on_close is None:
            return
        active.definition.on_close(active, reason, line, match, self)
        active.entry.closed = True
        active.entry.touch()

    def _append_fallback_line(self, line: LogLineInput) -> None:
        translator = self.source_spec(line.source).default_translate_line or plain_translate_line
        translation = translator(line, self)
        if translation is None:
            return
        self._append_translation(line.source, line.raw, translation)

    def _append_translation(self, source: str, raw: str, translation: LogLineTranslation) -> None:
        text = translation.text
        messages = list(translation.messages)
        if not messages and text:
            messages = [LogMessage(text=text, time=translation.time, tone=translation.tone, raw=translation.raw)]
        if not messages:
            return
        lines = translation.lines or [raw]
        entry = self.append_block(
            source,
            kind=translation.kind,
            title=translation.title,
            status=translation.status,
            time=translation.time,
            opened_at=translation.opened_at or translation.time,
            sealed_at=translation.sealed_at or translation.time,
            tone=translation.tone,
            messages=messages,
            lines=lines,
            raw=translation.raw,
            metadata=translation.metadata,
        )
        if translation.kind == "event" and not entry.title:
            entry.title = messages[0].text

    def _handle_terminal_update(self, raw: str, source: str, metadata: dict[str, object]) -> None:
        text = terminal_display_text(raw)
        if not text:
            return

        state = self._state(source)
        tone = _tone_from_metadata(metadata, "info")
        message = LogMessage(text=text, tone=tone, raw=text)
        timestamp = _metadata_str(metadata, "time") or current_datetime_text()
        if state.terminal_entry is None:
            state.terminal_entry = self.append_block(
                source,
                kind="line",
                status="default",
                time=timestamp,
                opened_at=timestamp,
                tone=tone,
                messages=[message],
                lines=[text],
                raw=text,
                closed=False,
            )
        else:
            state.terminal_entry.messages = [message]
            state.terminal_entry.lines = [text]
            state.terminal_entry.raw = text
            state.terminal_entry.tone = tone
            state.terminal_entry.touch()
            self.state_generation += 1

    def _finalize_terminal_update(self, source: str) -> None:
        state = self._state(source)
        entry = state.terminal_entry
        state.terminal_entry = None
        if entry is None:
            return
        entry.closed = True
        entry.sealed_at = current_datetime_text()
        entry.touch()
        self.state_generation += 1

    def _ensure_block_start_time(self, entry: LogEntry) -> None:
        if entry.time or entry.opened_at or entry.sealed_at:
            return
        now = current_datetime_text()
        entry.time = now
        entry.opened_at = now
        entry.touch()

    def _state(self, source: str) -> _SourceState:
        return self._source_states.setdefault(normalize_source(source), _SourceState())

    def _active_sources(self) -> list[str]:
        keys = set(self.sources)
        keys.update(self._source_states)
        keys.update(self.active_blocks)
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


def plain_translate_line(line: LogLineInput, context: LogPipelineSession) -> LogLineTranslation | None:
    source = line.source
    raw = line.raw
    metadata = line.metadata
    text = _metadata_str(metadata, "message_override") or terminal_display_text(raw)
    if not text:
        return None
    spec = context.source_spec(source)
    tone = _tone_from_metadata(metadata, spec.default_tone)
    kind = _metadata_str(metadata, "kind_override") or "line"
    time_text = _metadata_str(metadata, "time")
    if time_text is None:
        time_text = current_datetime_text()
    status = _status_from_metadata(metadata) or "default"
    title = _metadata_str(metadata, "title_override") or (text if kind != "line" else "")
    raw_value = raw if raw != text else None
    message = LogMessage(
        text=text,
        time=time_text,
        tone=tone,
        raw=raw_value,
        metadata=_metadata_dict(metadata, "message_metadata"),
    )
    return LogLineTranslation(
        text=text,
        kind=kind,
        title=title,
        status=status,
        time=time_text,
        opened_at=time_text,
        sealed_at=time_text,
        tone=tone,
        messages=[message],
        lines=[raw],
        raw=raw_value,
        metadata=_metadata_dict(metadata, "entry_metadata"),
    )


def framework_event_translate_line(line: LogLineInput, context: LogPipelineSession) -> LogLineTranslation | None:
    metadata = dict(line.metadata)
    metadata.setdefault("kind_override", "event")
    metadata.setdefault("tone", "info")
    translation = plain_translate_line(
        LogLineInput(
            raw=line.raw,
            source=line.source,
            metadata=metadata,
            default_tone=line.default_tone,
            processed=line.processed,
        ),
        context,
    )
    if translation is None:
        return None
    translation.title = translation.title or translation.text
    return translation


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


def current_datetime_text() -> str:
    return server_now_iso()


def terminal_display_text(raw: str) -> str:
    return ANSI_ESCAPE_RE.sub("", raw).strip()


def _call_matcher(
    matcher: EndMatcher | None,
    active: ActiveBlock,
    line: LogLineInput,
    session: LogPipelineSession,
) -> object | None:
    if matcher is None:
        return None
    return matcher(active, line, session)


def _is_match(match: object | None) -> bool:
    return match is not None and match is not False


def _trim_list(values: list[object], max_items: int) -> None:
    if max_items < 0:
        return
    overflow = len(values) - max_items
    if overflow > 0:
        del values[:overflow]


def _metadata_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _metadata_dict(metadata: dict[str, object], key: str) -> dict[str, object]:
    value = metadata.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _tone_from_metadata(metadata: dict[str, object], default: LogTone) -> LogTone:
    value = metadata.get("tone")
    return value if value in {"default", "success", "warning", "danger", "info", "theme"} else default


def _status_from_metadata(metadata: dict[str, object]) -> BlockStatus | None:
    value = metadata.get("status_override", metadata.get("status"))
    if value in {"default", "running", "succeeded", "failed", "stopped", "unknown", "unfinished", "warning"}:
        return value  # type: ignore[return-value]
    return None
