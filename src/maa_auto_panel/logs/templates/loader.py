from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from typing import Literal

from maa_auto_panel.logs.templates.model import (
    BoundaryRule,
    CompiledPattern,
    FieldSpec,
    FieldType,
    PLACEHOLDER_RE,
    PlaceholderStyle,
    SegmentTemplate,
    TONES,
    TemplateRule,
    TemplateValidationError,
    TranslationBlock,
    TranslationTemplate,
)


BLOCK_KEYS = {
    "translations",
    "rules",
    "start",
    "end",
    "kind",
    "title",
    "status",
    "tone",
    "message_tone",
    "panel_kind",
    "entry",
    "capture_start",
    "emit_start",
    "track_elapsed",
    "fallback_indent",
    "status_from_message_tone",
    "close_on_metadata",
}
RULE_KEYS = {
    "match",
    "action",
    "text",
    "tone",
    "indent",
    "styles",
    "segments",
    "lookups",
    "replacements",
    "values",
    "fold_group",
    "fold_role",
}
BOUNDARY_KEYS = {"source", "match", "values", "reprocess", "message", "message_tone"}


@dataclass(frozen=True)
class TolerantTemplateLoad:
    template: TranslationTemplate
    diagnostics: tuple[str, ...] = ()


def load_translation_template(path: Path) -> TranslationTemplate:
    data = read_template_data(path)
    if data.get("version") != 1 or isinstance(data.get("version"), bool):
        raise TemplateValidationError(path, "version", "must be 1")
    reject_unknown_keys(path, data, {"version", "global", "blocks"}, "document")

    global_definition = data.get("global")
    if not isinstance(global_definition, dict):
        raise TemplateValidationError(path, "global", "must be a table")
    reject_unknown_keys(path, global_definition, {"fields", "lookups", "translations", "rules"}, "global")
    fields = load_fields(path, global_definition.get("fields"), location="global.fields")
    lookups = load_lookups(path, global_definition.get("lookups"), location="global.lookups")
    translations = string_mapping(path, global_definition.get("translations"), "global.translations")
    rules = load_rules(path, global_definition.get("rules"), fields, lookups, location="global")
    blocks = load_blocks(path, data.get("blocks"), fields, lookups)
    return TranslationTemplate(path, fields, lookups, translations, tuple(rules), blocks)


def load_translation_template_tolerant(path: Path) -> TolerantTemplateLoad:
    """Load every independently valid template fragment and report discarded data.

    TOML syntax, file I/O, encoding, and unsupported document versions remain fatal
    because they do not provide a trustworthy object tree. Once TOML is decoded,
    invalid fields, rules, boundaries, and blocks are isolated so unrelated
    translations remain usable.
    """
    data = read_template_data(path)
    if data.get("version") != 1 or isinstance(data.get("version"), bool):
        raise TemplateValidationError(path, "version", "must be 1")

    diagnostics: list[str] = []
    clean_unknown_keys(path, data, {"version", "global", "blocks"}, "document", diagnostics)
    global_definition = data.get("global")
    if not isinstance(global_definition, dict):
        diagnostics.append(str(TemplateValidationError(path, "global", "must be a table")))
        global_definition = {}
    else:
        global_definition = clean_unknown_keys(
            path,
            global_definition,
            {"fields", "lookups", "translations", "rules"},
            "global",
            diagnostics,
        )

    fields = tolerant_fields(path, global_definition.get("fields"), diagnostics)
    lookups = tolerant_lookups(path, global_definition.get("lookups"), diagnostics)
    translations = tolerant_string_mapping(
        path,
        global_definition.get("translations"),
        "global.translations",
        diagnostics,
    )
    rules = tolerant_rules(path, global_definition.get("rules"), fields, lookups, location="global", diagnostics=diagnostics)
    blocks = tolerant_blocks(path, data.get("blocks"), fields, lookups, diagnostics)
    return TolerantTemplateLoad(
        TranslationTemplate(path, fields, lookups, translations, tuple(rules), blocks),
        tuple(diagnostics),
    )


def read_template_data(path: Path) -> dict[str, object]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise TemplateValidationError(path, "document", str(exc)) from exc


def load_blocks(
    path: Path,
    value: object,
    fields: dict[str, FieldSpec],
    lookups: dict[str, dict[str, str]],
) -> dict[str, TranslationBlock]:
    if not isinstance(value, dict) or not value:
        raise TemplateValidationError(path, "blocks", "must be a non-empty table")
    output: dict[str, TranslationBlock] = {}
    for name, raw in value.items():
        location = f"blocks.{name}"
        if not isinstance(raw, dict):
            raise TemplateValidationError(path, location, "must be a table")
        reject_unknown_keys(path, raw, BLOCK_KEYS, location)
        output[name] = load_block(path, name, raw, fields, lookups)
    return output


def load_block(
    path: Path,
    name: str,
    raw: dict[str, object],
    fields: dict[str, FieldSpec],
    lookups: dict[str, dict[str, str]],
    *,
    rules: list[TemplateRule] | None = None,
    start: list[BoundaryRule] | None = None,
    end: list[BoundaryRule] | None = None,
    translations: dict[str, str] | None = None,
) -> TranslationBlock:
    location = f"blocks.{name}"
    loaded_rules = load_rules(path, raw.get("rules"), fields, lookups, location=location) if rules is None else rules
    loaded_start = load_boundaries(path, raw.get("start"), location=location, boundary="start") if start is None else start
    loaded_end = load_boundaries(path, raw.get("end"), location=location, boundary="end") if end is None else end
    loaded_translations = (
        string_mapping(path, raw.get("translations"), f"{location}.translations")
        if translations is None
        else translations
    )
    kind = nonempty_string(path, raw.get("kind", name), f"{location}.kind")
    title = string_value(path, raw.get("title", ""), f"{location}.title")
    status = raw.get("status", "default")
    if status not in {"default", "running", "succeeded", "failed", "stopped", "unknown", "unfinished", "warning", None}:
        raise TemplateValidationError(path, f"{location}.status", "invalid block status")
    tone = tone_value(path, raw.get("tone", "default"), f"{location}.tone")
    message_tone = tone_value(path, raw.get("message_tone", "default"), f"{location}.message_tone")
    panel_kind = optional_nonempty_string(path, raw.get("panel_kind"), f"{location}.panel_kind")
    entry_fields = string_mapping(path, raw.get("entry"), f"{location}.entry")
    unknown_entry_fields = sorted(set(entry_fields) - {"title", "name", "task_id", "source_name"})
    if unknown_entry_fields:
        raise TemplateValidationError(path, f"{location}.entry.{unknown_entry_fields[0]}", "unknown field")
    captures = tuple(
        dict.fromkeys(capture for rule in (*loaded_start, *loaded_end) for capture in rule.pattern.captures)
    )
    validate_references(path, f"{location}.title", title, fields, captures)
    for field_name, field_template in entry_fields.items():
        validate_references(path, f"{location}.entry.{field_name}", field_template, fields, captures)
    return TranslationBlock(
        translations=loaded_translations,
        rules=tuple(loaded_rules),
        start=tuple(loaded_start),
        end=tuple(loaded_end),
        kind=kind,
        title=title,
        status=status,  # type: ignore[arg-type]
        tone=tone,
        message_tone=message_tone,
        panel_kind=panel_kind,
        entry_fields=entry_fields,
        capture_start=bool_value(path, raw.get("capture_start", False), f"{location}.capture_start"),
        emit_start=bool_value(path, raw.get("emit_start", False), f"{location}.emit_start"),
        track_elapsed=bool_value(path, raw.get("track_elapsed", False), f"{location}.track_elapsed"),
        fallback_indent=nonnegative_int(path, raw.get("fallback_indent", 0), f"{location}.fallback_indent"),
        status_from_message_tone=bool_value(
            path,
            raw.get("status_from_message_tone", False),
            f"{location}.status_from_message_tone",
        ),
        close_on_metadata=optional_nonempty_string(
            path,
            raw.get("close_on_metadata"),
            f"{location}.close_on_metadata",
        ),
    )


def tolerant_blocks(
    path: Path,
    value: object,
    fields: dict[str, FieldSpec],
    lookups: dict[str, dict[str, str]],
    diagnostics: list[str],
) -> dict[str, TranslationBlock]:
    if not isinstance(value, dict) or not value:
        diagnostics.append(str(TemplateValidationError(path, "blocks", "must be a non-empty table")))
        return {}
    output: dict[str, TranslationBlock] = {}
    for name, raw in value.items():
        location = f"blocks.{name}"
        if not isinstance(raw, dict):
            diagnostics.append(str(TemplateValidationError(path, location, "must be a table")))
            continue
        cleaned = clean_unknown_keys(path, raw, BLOCK_KEYS, location, diagnostics)
        rules = tolerant_rules(
            path,
            cleaned.get("rules"),
            fields,
            lookups,
            location=location,
            diagnostics=diagnostics,
        )
        start = tolerant_boundaries(
            path,
            cleaned.get("start"),
            location=location,
            boundary="start",
            diagnostics=diagnostics,
        )
        end = tolerant_boundaries(
            path,
            cleaned.get("end"),
            location=location,
            boundary="end",
            diagnostics=diagnostics,
        )
        translations = tolerant_string_mapping(
            path,
            cleaned.get("translations"),
            f"{location}.translations",
            diagnostics,
        )
        try:
            output[name] = load_block(
                path,
                name,
                cleaned,
                fields,
                lookups,
                rules=rules,
                start=start,
                end=end,
                translations=translations,
            )
        except TemplateValidationError as exc:
            diagnostics.append(str(exc))
    return output


def load_fields(path: Path, value: object, *, location: str) -> dict[str, FieldSpec]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TemplateValidationError(path, location, "must be a table")
    output: dict[str, FieldSpec] = {}
    for name, raw in value.items():
        field_location = f"{location}.{name}"
        if not isinstance(raw, dict):
            raise TemplateValidationError(path, field_location, "must be a table")
        reject_unknown_keys(path, raw, {"type", "external", "fallback"}, field_location)
        field_type = raw.get("type", "string")
        if field_type not in {"string", "integer", "boolean"}:
            raise TemplateValidationError(path, f"{field_location}.type", "must be string, integer, or boolean")
        external = bool_value(path, raw.get("external", False), f"{field_location}.external")
        fallback = raw.get("fallback")
        if fallback is not None and not valid_fallback(field_type, fallback):
            raise TemplateValidationError(path, f"{field_location}.fallback", f"must match field type {field_type}")
        output[name] = FieldSpec(name=name, field_type=field_type, external=external, fallback=fallback)  # type: ignore[arg-type]
    return output


def tolerant_fields(path: Path, value: object, diagnostics: list[str]) -> dict[str, FieldSpec]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        diagnostics.append(str(TemplateValidationError(path, "global.fields", "must be a table")))
        return {}
    output: dict[str, FieldSpec] = {}
    for name, raw in value.items():
        location = f"global.fields.{name}"
        if not isinstance(raw, dict):
            diagnostics.append(str(TemplateValidationError(path, location, "must be a table")))
            continue
        cleaned = clean_unknown_keys(path, raw, {"type", "external", "fallback"}, location, diagnostics)
        try:
            output.update(load_fields(path, {name: cleaned}, location="global.fields"))
        except TemplateValidationError as exc:
            diagnostics.append(str(exc))
    return output


def load_lookups(path: Path, value: object, *, location: str) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TemplateValidationError(path, location, "must be a table")
    output: dict[str, dict[str, str]] = {}
    for name, raw in value.items():
        if not isinstance(raw, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in raw.items()):
            raise TemplateValidationError(path, f"{location}.{name}", "must contain string values")
        output[name] = dict(raw)
    return output


def tolerant_lookups(path: Path, value: object, diagnostics: list[str]) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        diagnostics.append(str(TemplateValidationError(path, "global.lookups", "must be a table")))
        return {}
    output: dict[str, dict[str, str]] = {}
    for name, raw in value.items():
        try:
            output.update(load_lookups(path, {name: raw}, location="global.lookups"))
        except TemplateValidationError as exc:
            diagnostics.append(str(exc))
    return output


def load_rules(
    path: Path,
    value: object,
    fields: dict[str, FieldSpec],
    lookups: dict[str, dict[str, str]],
    *,
    location: str,
) -> list[TemplateRule]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TemplateValidationError(path, f"{location}.rules", "must be an array of tables")
    output: list[TemplateRule] = []
    for index, raw in enumerate(value):
        rule_location = f"{location}.rules[{index}]"
        if not isinstance(raw, dict):
            raise TemplateValidationError(path, rule_location, "must be a table")
        reject_unknown_keys(path, raw, RULE_KEYS, rule_location)
        output.append(load_rule(path, raw, fields, lookups, rule_location))
    return output


def load_rule(
    path: Path,
    raw: dict[str, object],
    fields: dict[str, FieldSpec],
    lookups: dict[str, dict[str, str]],
    rule_location: str,
) -> TemplateRule:
    pattern = compile_pattern(path, required_string(path, raw, "match", rule_location), f"{rule_location}.match")
    action = raw.get("action", "emit")
    if action not in {"emit", "drop"}:
        raise TemplateValidationError(path, f"{rule_location}.action", "must be emit or drop")
    text = string_value(path, raw.get("text", ""), f"{rule_location}.text")
    raw_values = raw.get("values")
    if raw_values is not None and not isinstance(raw_values, dict):
        raise TemplateValidationError(path, f"{rule_location}.values", "must be a table")
    values = dict(raw_values or {})
    references = pattern.captures + tuple(str(name) for name in values)
    validate_references(path, f"{rule_location}.text", text, fields, references)
    tone_raw = raw.get("tone")
    tone = None if tone_raw is None else tone_value(path, tone_raw, f"{rule_location}.tone")
    lookup_refs = string_mapping(path, raw.get("lookups"), f"{rule_location}.lookups")
    for capture, lookup_name in lookup_refs.items():
        if capture not in pattern.captures and capture not in fields:
            raise TemplateValidationError(path, f"{rule_location}.lookups.{capture}", "unknown field")
        if lookup_name not in lookups:
            raise TemplateValidationError(path, f"{rule_location}.lookups.{capture}", "unknown lookup")
    fold_role = raw.get("fold_role")
    if fold_role is not None and fold_role not in {"noise", "emit_once"}:
        raise TemplateValidationError(path, f"{rule_location}.fold_role", "must be noise or emit_once")
    return TemplateRule(
        location=rule_location,
        pattern=pattern,
        action=action,  # type: ignore[arg-type]
        text=text,
        tone=tone,
        indent=nonnegative_int(path, raw.get("indent", 0), f"{rule_location}.indent"),
        styles=load_styles(path, raw.get("styles"), rule_location, fields, references),
        segments=load_segments(path, raw.get("segments"), rule_location, fields, references),
        lookups=lookup_refs,
        replacements=load_replacements(path, raw.get("replacements"), rule_location),
        values=values,
        fold_group=optional_nonempty_string(path, raw.get("fold_group"), f"{rule_location}.fold_group"),
        fold_role=fold_role,  # type: ignore[arg-type]
    )


def tolerant_rules(
    path: Path,
    value: object,
    fields: dict[str, FieldSpec],
    lookups: dict[str, dict[str, str]],
    *,
    location: str,
    diagnostics: list[str],
) -> list[TemplateRule]:
    if value is None:
        return []
    if not isinstance(value, list):
        diagnostics.append(str(TemplateValidationError(path, f"{location}.rules", "must be an array of tables")))
        return []
    output: list[TemplateRule] = []
    for index, raw in enumerate(value):
        rule_location = f"{location}.rules[{index}]"
        if not isinstance(raw, dict):
            diagnostics.append(str(TemplateValidationError(path, rule_location, "must be a table")))
            continue
        cleaned = clean_unknown_keys(path, raw, RULE_KEYS, rule_location, diagnostics)
        try:
            output.append(load_rule(path, cleaned, fields, lookups, rule_location))
        except TemplateValidationError as exc:
            diagnostics.append(str(exc))
    return output


def load_boundaries(
    path: Path,
    value: object,
    *,
    location: str,
    boundary: Literal["start", "end"],
) -> list[BoundaryRule]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TemplateValidationError(path, f"{location}.{boundary}", "must be an array of tables")
    output: list[BoundaryRule] = []
    for index, raw in enumerate(value):
        item_location = f"{location}.{boundary}[{index}]"
        if not isinstance(raw, dict):
            raise TemplateValidationError(path, item_location, "must be a table")
        reject_unknown_keys(path, raw, BOUNDARY_KEYS, item_location)
        output.append(load_boundary(path, raw, item_location))
    return output


def load_boundary(path: Path, raw: dict[str, object], item_location: str) -> BoundaryRule:
    raw_values = raw.get("values")
    if raw_values is not None and not isinstance(raw_values, dict):
        raise TemplateValidationError(path, f"{item_location}.values", "must be a table")
    return BoundaryRule(
        location=item_location,
        source=required_string(path, raw, "source", item_location),
        pattern=compile_pattern(path, required_string(path, raw, "match", item_location), f"{item_location}.match"),
        values=dict(raw_values or {}),
        reprocess=bool_value(path, raw.get("reprocess", False), f"{item_location}.reprocess"),
        message=optional_nonempty_string(path, raw.get("message"), f"{item_location}.message"),
        message_tone=tone_value(path, raw.get("message_tone", "default"), f"{item_location}.message_tone"),
    )


def tolerant_boundaries(
    path: Path,
    value: object,
    *,
    location: str,
    boundary: Literal["start", "end"],
    diagnostics: list[str],
) -> list[BoundaryRule]:
    if value is None:
        return []
    if not isinstance(value, list):
        diagnostics.append(str(TemplateValidationError(path, f"{location}.{boundary}", "must be an array of tables")))
        return []
    output: list[BoundaryRule] = []
    for index, raw in enumerate(value):
        item_location = f"{location}.{boundary}[{index}]"
        if not isinstance(raw, dict):
            diagnostics.append(str(TemplateValidationError(path, item_location, "must be a table")))
            continue
        cleaned = clean_unknown_keys(path, raw, BOUNDARY_KEYS, item_location, diagnostics)
        try:
            output.append(load_boundary(path, cleaned, item_location))
        except TemplateValidationError as exc:
            diagnostics.append(str(exc))
    return output


def compile_pattern(path: Path, source: str, location: str) -> CompiledPattern:
    parts: list[str] = []
    captures: list[str] = []
    kinds: list[str] = []
    cursor = 0
    matches = list(PLACEHOLDER_RE.finditer(source))
    for index, match in enumerate(matches):
        parts.append(re.escape(source[cursor : match.start()]))
        name = match.group("name")
        if "." in name:
            raise TemplateValidationError(path, location, "match capture names cannot contain dots")
        if name in captures:
            raise TemplateValidationError(path, location, f"duplicate capture: {name}")
        kind = match.group("kind") or "text"
        captures.append(name)
        kinds.append(kind)
        expression = r"\d+" if kind == "int" else r"\S+" if kind == "word" else (r".*" if index == len(matches) - 1 else r".*?")
        parts.append(f"(?P<{name}>{expression})")
        cursor = match.end()
    parts.append(re.escape(source[cursor:]))
    return CompiledPattern(source, re.compile("".join(parts)), tuple(captures), tuple(kinds))


def load_styles(
    path: Path,
    value: object,
    location: str,
    fields: dict[str, FieldSpec],
    captures: tuple[str, ...],
) -> dict[str, PlaceholderStyle]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TemplateValidationError(path, f"{location}.styles", "must be a table")
    output: dict[str, PlaceholderStyle] = {}
    for name, raw in value.items():
        item_location = f"{location}.styles.{name}"
        if name not in captures and name not in fields:
            raise TemplateValidationError(path, item_location, "unknown field")
        if not isinstance(raw, dict):
            raise TemplateValidationError(path, item_location, "must be a table")
        reject_unknown_keys(path, raw, {"tone", "strong"}, item_location)
        output[name] = PlaceholderStyle(
            tone=tone_value(path, raw.get("tone", "default"), f"{item_location}.tone"),
            strong=bool_value(path, raw.get("strong", False), f"{item_location}.strong"),
        )
    return output


def load_segments(
    path: Path,
    value: object,
    location: str,
    fields: dict[str, FieldSpec],
    captures: tuple[str, ...],
) -> tuple[SegmentTemplate, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TemplateValidationError(path, f"{location}.segments", "must be an array")
    output: list[SegmentTemplate] = []
    for index, raw in enumerate(value):
        item_location = f"{location}.segments[{index}]"
        if not isinstance(raw, dict):
            raise TemplateValidationError(path, item_location, "must be a table")
        reject_unknown_keys(path, raw, {"text", "tone", "strong"}, item_location)
        text = required_string(path, raw, "text", item_location)
        validate_references(path, f"{item_location}.text", text, fields, captures)
        output.append(
            SegmentTemplate(
                text,
                tone_value(path, raw.get("tone", "default"), f"{item_location}.tone"),
                bool_value(path, raw.get("strong", False), f"{item_location}.strong"),
            )
        )
    return tuple(output)


def load_replacements(path: Path, value: object, location: str) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TemplateValidationError(path, f"{location}.replacements", "must be a table")
    output: dict[str, dict[str, str]] = {}
    for field_name, raw in value.items():
        if not isinstance(raw, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in raw.items()):
            raise TemplateValidationError(path, f"{location}.replacements.{field_name}", "must contain string values")
        output[field_name] = dict(raw)
    return output


def validate_references(
    path: Path,
    location: str,
    text: str,
    fields: dict[str, FieldSpec],
    captures: tuple[str, ...],
) -> None:
    allowed = set(fields) | set(captures)
    for match in PLACEHOLDER_RE.finditer(text):
        if match.group("name") not in allowed:
            raise TemplateValidationError(path, location, f"unknown field: {match.group('name')}")


def required_string(path: Path, raw: dict[str, object], key: str, location: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise TemplateValidationError(path, f"{location}.{key}", "must be a non-empty string")
    return value


def reject_unknown_keys(path: Path, raw: dict[str, object], allowed: set[str], location: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise TemplateValidationError(path, f"{location}.{unknown[0]}", "unknown field")


def clean_unknown_keys(
    path: Path,
    raw: dict[str, object],
    allowed: set[str],
    location: str,
    diagnostics: list[str],
) -> dict[str, object]:
    for key in sorted(set(raw) - allowed):
        diagnostics.append(str(TemplateValidationError(path, f"{location}.{key}", "unknown field ignored")))
    return {key: value for key, value in raw.items() if key in allowed}


def string_mapping(path: Path, value: object, location: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise TemplateValidationError(path, location, "must contain string values")
    return dict(value)


def tolerant_string_mapping(
    path: Path,
    value: object,
    location: str,
    diagnostics: list[str],
) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        diagnostics.append(str(TemplateValidationError(path, location, "must be a table with string values")))
        return {}
    output: dict[str, str] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, str):
            output[key] = item
        else:
            diagnostics.append(str(TemplateValidationError(path, f"{location}.{key}", "must be a string")))
    return output


def string_value(path: Path, value: object, location: str) -> str:
    if not isinstance(value, str):
        raise TemplateValidationError(path, location, "must be a string")
    return value


def nonempty_string(path: Path, value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise TemplateValidationError(path, location, "must be a non-empty string")
    return value


def optional_nonempty_string(path: Path, value: object, location: str) -> str | None:
    if value is None:
        return None
    return nonempty_string(path, value, location)


def bool_value(path: Path, value: object, location: str) -> bool:
    if not isinstance(value, bool):
        raise TemplateValidationError(path, location, "must be a boolean")
    return value


def nonnegative_int(path: Path, value: object, location: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TemplateValidationError(path, location, "must be a non-negative integer")
    return value


def tone_value(path: Path, value: object, location: str):
    if value not in TONES:
        raise TemplateValidationError(path, location, "invalid tone")
    return value  # type: ignore[return-value]


def valid_fallback(field_type: FieldType, value: object) -> bool:
    if field_type == "string":
        return isinstance(value, str)
    if field_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, bool)
