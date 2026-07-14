from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Literal

from maa_auto_panel.logs.pipeline import (
    ActiveBlock,
    BlockDefinition,
    BlockStartContext,
    BlockStartOutcome,
    CloseReason,
    LogLineInput,
    LogLineTranslation,
    LogPipelineSession,
    LogSourceSpec,
    default_tone_for_source,
    plain_translate_line,
)
from maa_auto_panel.logs.records import BlockStatus, LogMessage, LogTone
from maa_auto_panel.logs.templates.engine import TranslationEngine, template_fields
from maa_auto_panel.logs.templates.model import BoundaryRule, TranslationFieldMonitor, TranslationTemplate


@dataclass(frozen=True)
class TemplateBoundaryMatch:
    block: str
    boundary: Literal["start", "end"]
    rule: BoundaryRule
    captures: dict[str, object]

    @property
    def reprocess(self) -> bool:
        return self.rule.reprocess


@dataclass(frozen=True)
class _MetadataBoundary:
    reprocess: bool = True


class TemplateBlockRuntime:
    """Register compiled template blocks and apply them to a streaming log pipeline."""

    context_key = "translation_template_runtime"

    def __init__(
        self,
        template: TranslationTemplate,
        monitor: TranslationFieldMonitor | None = None,
        *,
        fallback_block: str,
    ) -> None:
        self.engine = TranslationEngine(template, monitor)
        self.template = template
        self.fallback_block = fallback_block

    def register(self, session: LogPipelineSession) -> None:
        session.context[self.context_key] = self
        for block_name, block in self.template.blocks.items():
            if not block.start:
                continue
            sources = {rule.source for rule in (*block.start, *block.end)}
            session.register_block(
                BlockDefinition(
                    kind=block.kind,
                    source_predicate=lambda source, allowed=frozenset(sources): source in allowed,
                    start_matcher=lambda line, current, name=block_name: self._match_start(name, line),
                    end_matcher=lambda active, line, current, name=block_name: self._match_end(name, active, line),
                    passive_boundary_matcher=(
                        lambda active, line, current, key=block.close_on_metadata: _MetadataBoundary()
                        if key and bool(line.metadata.get(key))
                        else None
                    ),
                    translate_line=lambda active, line, current, name=block_name: self._translate_block_line(
                        name, active, line, current
                    ),
                    on_start=lambda active, line, match, context, name=block_name: self._on_start(
                        name, active, line, match, context
                    ),
                    on_close=lambda active, reason, line, match, current, name=block_name: self._on_close(
                        name, active, reason, line, match, current
                    ),
                    default_title=block.title,
                    default_status=block.status,
                    default_tone=block.tone,
                    rule_id=f"template:{block_name}",
                    panel_kind=block.panel_kind,
                )
            )

    def translate_fallback(self, line: LogLineInput, session: LogPipelineSession) -> LogLineTranslation | None:
        if "message_override" in line.metadata or "kind_override" in line.metadata:
            return plain_translate_line(line, session)
        base = plain_translate_line(line, session)
        if base is None:
            return None
        result = self.engine.translate(
            line.source,
            line.content,
            block=self.fallback_block,
            default_tone=line.tone,
            time=line.time,
            raw=line.raw,
        )
        if result.message is None:
            return None
        message = result.message
        metadata = line.metadata.get("message_metadata")
        message.metadata = dict(metadata) if isinstance(metadata, dict) else {}
        base.text = message.text
        base.time = message.time or base.time
        base.tone = message.tone
        base.messages = [message]
        base.lines = [line.raw]
        base.raw = message.raw
        return base

    def _match_start(self, block_name: str, line: LogLineInput) -> TemplateBoundaryMatch | None:
        block = self.template.blocks[block_name]
        matched = self._match_rules(block_name, "start", block.start, line)
        return matched if matched is not None else self._match_rules(block_name, "end", block.end, line)

    def _match_end(self, block_name: str, active: ActiveBlock, line: LogLineInput) -> TemplateBoundaryMatch | None:
        block = self.template.blocks[block_name]
        matched = self._match_rules(block_name, "end", block.end, line)
        if matched is None:
            return None
        source_name = matched.captures.get("source_name")
        current_name = active.entry.source_name or active.entry.name
        if source_name is not None and current_name and str(source_name) != current_name:
            return None
        return matched

    @staticmethod
    def _match_rules(
        block_name: str,
        boundary: Literal["start", "end"],
        rules: tuple[BoundaryRule, ...],
        line: LogLineInput,
    ) -> TemplateBoundaryMatch | None:
        for rule in rules:
            if rule.source != line.source:
                continue
            captures = rule.pattern.match(line.content)
            if captures is not None:
                return TemplateBoundaryMatch(block_name, boundary, rule, captures)
        return None

    def _on_start(
        self,
        block_name: str,
        active: ActiveBlock,
        line: LogLineInput,
        match: object | None,
        context: BlockStartContext,
    ) -> BlockStartOutcome:
        if not isinstance(match, TemplateBoundaryMatch):
            return BlockStartOutcome()
        block = self.template.blocks[block_name]
        fields = dict(match.rule.values)
        required = tuple(
            dict.fromkeys(
                field
                for value in (block.title, *block.entry_fields.values())
                for field in template_fields(value)
            )
        )
        fields = self.engine.complete_fields(
            context=f"{block_name}.{match.boundary}",
            rule_location=match.rule.location,
            source=line.source,
            captures=match.captures,
            fields=fields,
            required_fields=required,
            block_id=active.entry.id,
        )
        fields.update(match.captures)
        active.context["template_fields"] = fields
        for entry_field, value_template in {"title": block.title, **block.entry_fields}.items():
            if not value_template:
                continue
            rendered, fields = self.engine.render_text(
                value_template,
                rule_location=match.rule.location,
                source=line.source,
                captures=match.captures,
                fields=fields,
                block_id=active.entry.id,
            )
            setattr(active.entry, entry_field, rendered if entry_field == "title" else (rendered or None))
        status = match.rule.values.get("status", block.status)
        if _is_block_status(status):
            active.entry.status = status  # type: ignore[assignment]
            active.entry.tone = tone_for_status(status, block.tone)  # type: ignore[arg-type]
        active.entry.time = line.time
        if block.capture_start or block.emit_start:
            context.session.append_active_record(active, line=line.raw)
        if block.emit_start:
            self._append_translated_message(block_name, active, line, context.session)
        if block.track_elapsed and active.entry.status == "running":
            started = time.monotonic()
            active.entry.metadata["started_monotonic"] = started
            active.context["started_monotonic"] = started
        if match.boundary == "end":
            active.entry.sealed_at = line.time
            active.entry.closed = True
            if match.rule.message:
                context.session.append_active_record(
                    active,
                    message=LogMessage(
                        text=match.rule.message,
                        time=line.time,
                        tone=match.rule.message_tone,
                        raw=line.raw,
                    ),
                )
            active.locked_fields.update({"status", "tone", "sealed_at"})
            return BlockStartOutcome(keep_active=False)
        active.entry.opened_at = line.time or active.entry.opened_at
        return BlockStartOutcome()

    def _translate_block_line(
        self,
        block_name: str,
        active: ActiveBlock,
        line: LogLineInput,
        session: LogPipelineSession,
    ) -> None:
        self._append_translated_message(block_name, active, line, session)

    def _append_translated_message(
        self,
        block_name: str,
        active: ActiveBlock,
        line: LogLineInput,
        session: LogPipelineSession,
    ) -> LogMessage | None:
        block = self.template.blocks[block_name]
        if not (block.capture_start or block.emit_start) or active.entry.lines[-1:] != [line.raw]:
            session.append_active_record(active, line=line.raw)
        fields = active.context.get("template_fields")
        result = self.engine.translate(
            line.source,
            line.content,
            block=block_name,
            fields=dict(fields) if isinstance(fields, dict) else {},
            default_tone=line.tone if line.tone != "default" else block.message_tone,
            time=line.time,
            raw=line.raw,
            block_id=active.entry.id,
            fold_state=active.context,
        )
        message = result.message
        if message is None:
            return None
        if not result.matched and block.fallback_indent:
            message.indent = block.fallback_indent
        session.append_active_record(active, message=message)
        if block.status_from_message_tone:
            if message.tone == "danger":
                active.entry.status = "failed"
                active.entry.tone = "danger"
            elif message.tone == "warning" and active.entry.status != "failed":
                active.entry.status = "stopped"
                active.entry.tone = "warning"
        return message

    def _on_close(
        self,
        block_name: str,
        active: ActiveBlock,
        reason: CloseReason,
        line: LogLineInput | None,
        match: object | None,
        session: LogPipelineSession,
    ) -> None:
        block = self.template.blocks[block_name]
        boundary = match if isinstance(match, TemplateBoundaryMatch) else None
        if boundary is not None:
            status = boundary.rule.values.get("status")
            if _is_block_status(status):
                active.entry.status = status  # type: ignore[assignment]
            if boundary.rule.message and line is not None:
                session.append_active_record(
                    active,
                    message=LogMessage(
                        text=boundary.rule.message,
                        time=line.time,
                        tone=boundary.rule.message_tone,
                        raw=line.raw,
                    ),
                )
        elif active.entry.status == "running":
            active.entry.status = "unfinished"
        active.entry.tone = tone_for_status(active.entry.status, block.tone)
        active.entry.metadata.pop("started_monotonic", None)
        active.context.pop("started_monotonic", None)
        active.locked_fields.update({"status", "tone", "sealed_at"})


def template_translate_line(line: LogLineInput, session: LogPipelineSession) -> LogLineTranslation | None:
    runtime = session.context.get(TemplateBlockRuntime.context_key)
    return runtime.translate_fallback(line, session) if isinstance(runtime, TemplateBlockRuntime) else plain_translate_line(line, session)


def template_source_spec(source: str, *, preprocess_line=None) -> LogSourceSpec:
    return LogSourceSpec(
        source,
        default_tone_for_source(source),
        template_translate_line,
        preprocess_line=preprocess_line,
    )


def tone_for_status(status: BlockStatus | None, default: LogTone) -> LogTone:
    if status == "succeeded":
        return "success"
    if status == "failed":
        return "danger"
    if status in {"stopped", "unknown", "unfinished", "warning"}:
        return "warning"
    return default


def _is_block_status(value: object) -> bool:
    return value in {"default", "running", "succeeded", "failed", "stopped", "unknown", "unfinished", "warning"}
