from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Literal, Protocol

from maa_auto_panel.logs.records import BlockStatus, LogMessage, LogTone


FieldType = Literal["string", "integer", "boolean"]
PLACEHOLDER_RE = re.compile(r"\{(?P<name>[A-Za-z_][A-Za-z0-9_.]*)(?::(?P<kind>text|word|int))?\}")
TONES: set[str] = {"default", "success", "warning", "danger", "info", "theme"}


class TemplateValidationError(ValueError):
    def __init__(self, path: Path, location: str, message: str) -> None:
        self.path = path
        self.location = location
        self.message = message
        super().__init__(f"{path}: {location}: {message}")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    field_type: FieldType = "string"
    external: bool = False
    fallback: object | None = None


@dataclass(frozen=True)
class PlaceholderStyle:
    tone: LogTone = "default"
    strong: bool = False


@dataclass(frozen=True)
class SegmentTemplate:
    text: str
    tone: LogTone = "default"
    strong: bool = False


@dataclass(frozen=True)
class CompiledPattern:
    source: str
    regex: re.Pattern[str]
    captures: tuple[str, ...]
    capture_kinds: tuple[str, ...]

    def match(self, text: str) -> dict[str, object] | None:
        matched = self.regex.fullmatch(text)
        if matched is None:
            return None
        return {
            name: int(value) if kind == "int" else value
            for name, kind, value in zip(self.captures, self.capture_kinds, matched.groups(), strict=True)
        }


@dataclass(frozen=True)
class TemplateRule:
    location: str
    pattern: CompiledPattern
    action: Literal["emit", "drop"] = "emit"
    text: str = ""
    tone: LogTone | None = None
    indent: int = 0
    styles: dict[str, PlaceholderStyle] = field(default_factory=dict)
    segments: tuple[SegmentTemplate, ...] = ()
    lookups: dict[str, str] = field(default_factory=dict)
    replacements: dict[str, dict[str, str]] = field(default_factory=dict)
    values: dict[str, object] = field(default_factory=dict)
    fold_group: str | None = None
    fold_role: Literal["noise", "emit_once"] | None = None


@dataclass(frozen=True)
class BoundaryRule:
    location: str
    source: str
    pattern: CompiledPattern
    values: dict[str, object] = field(default_factory=dict)
    reprocess: bool = False
    message: str | None = None
    message_tone: LogTone = "default"


@dataclass(frozen=True)
class TranslationBlock:
    translations: dict[str, str]
    rules: tuple[TemplateRule, ...]
    start: tuple[BoundaryRule, ...]
    end: tuple[BoundaryRule, ...]
    kind: str
    title: str = ""
    status: BlockStatus | None = "default"
    tone: LogTone = "default"
    message_tone: LogTone = "default"
    panel_kind: str | None = None
    entry_fields: dict[str, str] = field(default_factory=dict)
    capture_start: bool = False
    emit_start: bool = False
    track_elapsed: bool = False
    fallback_indent: int = 0
    status_from_message_tone: bool = False
    close_on_metadata: str | None = None


@dataclass(frozen=True)
class TranslationTemplate:
    path: Path
    fields: dict[str, FieldSpec]
    lookups: dict[str, dict[str, str]]
    translations: dict[str, str]
    rules: tuple[TemplateRule, ...]
    blocks: dict[str, TranslationBlock]

    def rules_for(self, block: str) -> tuple[TemplateRule, ...]:
        definition = self.blocks.get(block)
        return self.rules + (definition.rules if definition is not None else ())

    def exact_translation(self, block: str, text: str) -> tuple[str, str] | None:
        if text in self.translations:
            return self.translations[text], f"global.translations.{text}"
        definition = self.blocks.get(block)
        if definition is None or text not in definition.translations:
            return None
        return definition.translations[text], f"blocks.{block}.translations.{text}"


@dataclass(frozen=True)
class MissingFieldsRequest:
    context: str
    rule_location: str
    source: str
    captures: dict[str, object]
    fields: dict[str, object]
    missing_fields: tuple[str, ...]
    block_id: str | None = None


class TranslationFieldMonitor(Protocol):
    def resolve_missing_fields(self, request: MissingFieldsRequest) -> dict[str, object]: ...


@dataclass(frozen=True)
class MatchedBoundary:
    rule_location: str
    source: str
    captures: dict[str, object]
    values: dict[str, object]


@dataclass(frozen=True)
class TranslationResult:
    matched: bool
    message: LogMessage | None
    rule_location: str | None = None
