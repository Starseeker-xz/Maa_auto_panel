from __future__ import annotations

import re
from typing import Literal

from maa_auto_panel.logs.records import LogMessage, LogTone
from maa_auto_panel.logs.templates.model import (
    FieldSpec,
    MatchedBoundary,
    MissingFieldsRequest,
    PLACEHOLDER_RE,
    TemplateRule,
    TranslationFieldMonitor,
    TranslationResult,
    TranslationTemplate,
)


class TranslationEngine:
    """Render a compiled template, consulting a domain monitor only for external fields."""

    def __init__(self, template: TranslationTemplate, monitor: TranslationFieldMonitor | None = None) -> None:
        self.template = template
        self.monitor = monitor
        self.diagnostics: list[str] = []

    def match_start(self, block: str, source: str, text: str) -> MatchedBoundary | None:
        return self._match_boundary(block, "start", source, text)

    def match_end(self, block: str, source: str, text: str) -> MatchedBoundary | None:
        return self._match_boundary(block, "end", source, text)

    def _match_boundary(
        self,
        block: str,
        boundary: Literal["start", "end"],
        source: str,
        text: str,
    ) -> MatchedBoundary | None:
        definition = self.template.blocks.get(block)
        if definition is None:
            return None
        rules = definition.start if boundary == "start" else definition.end
        for rule in rules:
            if rule.source != source:
                continue
            captures = rule.pattern.match(text)
            if captures is not None:
                return MatchedBoundary(rule.location, source, captures, dict(rule.values))
        return None

    def complete_fields(
        self,
        *,
        context: str,
        rule_location: str,
        source: str,
        captures: dict[str, object],
        fields: dict[str, object],
        required_fields: tuple[str, ...],
        block_id: str | None = None,
    ) -> dict[str, object]:
        output = dict(fields)
        output.update(captures)
        missing = tuple(
            name
            for name in required_fields
            if name not in output and (spec := self.template.fields.get(name)) is not None and spec.external
        )
        if not missing or self.monitor is None:
            return output
        request = MissingFieldsRequest(context, rule_location, source, dict(captures), dict(output), missing, block_id)
        try:
            patch = self.monitor.resolve_missing_fields(request)
        except Exception as exc:  # display extensions must never affect run results
            self.diagnostics.append(f"field monitor failed at {rule_location}: {exc}")
            return output
        for key, value in patch.items():
            spec = self.template.fields.get(key)
            if key not in missing or spec is None or not spec.external:
                continue
            if not valid_field_value(spec, value):
                self.diagnostics.append(f"field monitor returned invalid value at {rule_location}: field={key}")
                continue
            output[key] = value
        return output

    def render_text(
        self,
        template: str,
        *,
        rule_location: str,
        source: str,
        captures: dict[str, object],
        fields: dict[str, object],
        block_id: str | None = None,
        lookups: dict[str, str] | None = None,
        replacements: dict[str, dict[str, str]] | None = None,
    ) -> tuple[str, dict[str, object]]:
        resolved_fields = dict(fields)
        resolved_fields.update(captures)
        lookup_names = lookups or {}
        replacement_sets = replacements or {}

        def replace(match: re.Match[str]) -> str:
            name = match.group("name")
            value = self._resolve_field(name, rule_location, source, captures, resolved_fields, block_id)
            resolved_fields[name] = value
            text = str(value)
            lookup_name = lookup_names.get(name)
            if lookup_name:
                text = self.template.lookups.get(lookup_name, {}).get(text, text)
            for old, new in replacement_sets.get(name, {}).items():
                text = text.replace(old, new)
            return text

        return PLACEHOLDER_RE.sub(replace, template), resolved_fields

    def translate(
        self,
        source: str,
        text: str,
        *,
        block: str,
        fields: dict[str, object] | None = None,
        default_tone: LogTone = "default",
        time: str | None = None,
        raw: str | None = None,
        block_id: str | None = None,
        fold_state: dict[str, object] | None = None,
    ) -> TranslationResult:
        base_fields = dict(fields or {})
        exact = self.template.exact_translation(block, text)
        if exact is not None:
            translated, location = exact
            return TranslationResult(True, LogMessage(text=translated, time=time, tone=default_tone), location)
        for rule in self.template.rules_for(block):
            captures = rule.pattern.match(text)
            if captures is None:
                continue
            state = fold_state if fold_state is not None else {}
            if rule.fold_group is None:
                state.pop("active_fold_group", None)
                state.pop("fold_emitted", None)
            else:
                if state.get("active_fold_group") != rule.fold_group:
                    state["active_fold_group"] = rule.fold_group
                    state["fold_emitted"] = False
                if rule.fold_role == "noise":
                    return TranslationResult(True, None, rule.location)
                if rule.fold_role == "emit_once" and state.get("fold_emitted"):
                    return TranslationResult(True, None, rule.location)
                if rule.fold_role == "emit_once":
                    state["fold_emitted"] = True

            resolved_values = dict(base_fields)
            resolved_values.update(rule.values)
            resolved_values = self.complete_fields(
                context=f"{block}.translation",
                rule_location=rule.location,
                source=source,
                captures=captures,
                fields=resolved_values,
                required_fields=template_fields(rule.text),
                block_id=block_id,
            )
            if rule.action == "drop":
                return TranslationResult(True, None, rule.location)
            rendered, resolved = self.render_text(
                rule.text,
                rule_location=rule.location,
                source=source,
                captures=captures,
                fields=resolved_values,
                block_id=block_id,
                lookups=rule.lookups,
                replacements=rule.replacements,
            )
            if rule.segments:
                segments = []
                for segment_template in rule.segments:
                    segment_text, _ = self.render_text(
                        segment_template.text,
                        rule_location=rule.location,
                        source=source,
                        captures=captures,
                        fields=resolved,
                        block_id=block_id,
                        lookups=rule.lookups,
                        replacements=rule.replacements,
                    )
                    segment: dict[str, object] = {"text": segment_text}
                    if segment_template.tone != "default":
                        segment["tone"] = segment_template.tone
                    if segment_template.strong:
                        segment["strong"] = True
                    segments.append(segment)
            else:
                segments = render_segments(rule, rendered, resolved, self.template.lookups)
            return TranslationResult(
                True,
                LogMessage(
                    text=rendered,
                    time=time,
                    tone=rule.tone or default_tone,
                    segments=segments,
                    indent=rule.indent,
                ),
                rule.location,
            )
        if fold_state is not None:
            fold_state.pop("active_fold_group", None)
            fold_state.pop("fold_emitted", None)
        return TranslationResult(False, LogMessage(text=text, time=time, tone=default_tone, raw=raw or text))

    def _resolve_field(
        self,
        name: str,
        rule_location: str,
        source: str,
        captures: dict[str, object],
        fields: dict[str, object],
        block_id: str | None,
    ) -> object:
        if name in fields:
            return fields[name]
        spec = self.template.fields.get(name)
        if spec is None:
            raise KeyError(f"undeclared template field: {name}")
        fallback = spec.fallback
        if isinstance(fallback, str) and "{" in fallback:
            fallback, _ = self.render_text(
                fallback,
                rule_location=rule_location,
                source=source,
                captures=captures,
                fields=fields,
                block_id=block_id,
            )
        return fallback if fallback is not None else field_default(spec.field_type)


def template_fields(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.group("name") for match in PLACEHOLDER_RE.finditer(text)))


def render_segments(
    rule: TemplateRule,
    rendered: str,
    fields: dict[str, object],
    lookups: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    if not rule.styles:
        return []
    segments: list[dict[str, object]] = []
    cursor = 0
    for match in PLACEHOLDER_RE.finditer(rule.text):
        if match.start() > cursor:
            segments.append({"text": rule.text[cursor : match.start()]})
        name = match.group("name")
        value = str(fields.get(name, ""))
        lookup_name = rule.lookups.get(name)
        if lookup_name:
            value = lookups.get(lookup_name, {}).get(value, value)
        for old, new in rule.replacements.get(name, {}).items():
            value = value.replace(old, new)
        segment: dict[str, object] = {"text": value}
        style = rule.styles.get(name)
        if style is not None:
            if style.tone != "default":
                segment["tone"] = style.tone
            if style.strong:
                segment["strong"] = True
        segments.append(segment)
        cursor = match.end()
    if cursor < len(rule.text):
        segments.append({"text": rule.text[cursor:]})
    return segments if "".join(str(item["text"]) for item in segments) == rendered else []


def valid_field_value(spec: FieldSpec, value: object) -> bool:
    if spec.field_type == "string":
        return isinstance(value, str)
    if spec.field_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, bool)


def field_default(field_type: str) -> object:
    if field_type == "integer":
        return 0
    if field_type == "boolean":
        return False
    return ""
