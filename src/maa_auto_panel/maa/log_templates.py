from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from maa_auto_panel.logs.pipeline import LogSourceSpec
from maa_auto_panel.logs.templates.loader import load_translation_template
from maa_auto_panel.logs.templates.model import MissingFieldsRequest, TranslationFieldMonitor, TranslationTemplate
from maa_auto_panel.logs.templates.runtime import TemplateBlockRuntime, template_source_spec
from maa_auto_panel.time_utils import server_datetime_from_text

if TYPE_CHECKING:
    from maa_auto_panel.logs.state import RunLogBuffer


LOG_LINE_RE = re.compile(
    r"^\[(?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>[A-Z]+)\s*\]\s*(?P<body>.*)$"
)

LEVEL_TONE = {
    "ERROR": "danger",
    "WARN": "warning",
    "INFO": "info",
}


@dataclass
class MaaLogState(TranslationFieldMonitor):
    """Supplies task identity that cannot be inferred from repeated maa-cli task types."""

    expected_by_source: dict[str, deque[dict[str, str]]] = field(default_factory=lambda: defaultdict(deque))

    def begin_task_sequence(self, tasks: list[dict[str, str]]) -> None:
        self.expected_by_source.clear()
        for task in tasks:
            source_name = str(task.get("source_name") or task.get("type") or task.get("name") or "")
            if not source_name:
                continue
            self.expected_by_source[source_name].append(
                {
                    "task_id": str(task.get("task_id") or ""),
                    "source_name": source_name,
                    "name": str(task.get("name") or source_name),
                }
            )

    def resolve_missing_fields(self, request: MissingFieldsRequest) -> dict[str, object]:
        if request.context not in {"task.start", "task.end"}:
            return {}
        source_name = str(request.captures.get("source_name") or "")
        queue = self.expected_by_source.get(source_name)
        task = queue.popleft() if queue else {"task_id": "", "source_name": source_name, "name": source_name}
        values: dict[str, object] = {
            "task.id": task["task_id"],
            "task.name": task["name"],
            "task.source_name": task["source_name"],
        }
        return {name: values[name] for name in request.missing_fields if name in values}


def maa_log_source_specs() -> tuple[LogSourceSpec, ...]:
    return tuple(
        template_source_spec(source, preprocess_line=parse_log_line)
        for source in ("maa-cli:stdout", "maa-cli:stderr")
    )


def configure_maa_log_template(log: "RunLogBuffer") -> MaaLogState:
    state = MaaLogState()
    runtime = TemplateBlockRuntime(maa_translation_template(), state, fallback_block="task")
    log.pipeline.context["maa_log_state"] = state
    runtime.register(log.pipeline)
    return state


def begin_maa_task_sequence(log: "RunLogBuffer", tasks: list[dict[str, str]]) -> None:
    state = log.pipeline.context.get("maa_log_state")
    if not isinstance(state, MaaLogState):
        raise RuntimeError("MAA log template must be configured before its task sequence")
    state.begin_task_sequence(tasks)


@lru_cache(maxsize=1)
def maa_translation_template() -> TranslationTemplate:
    return load_translation_template(Path(__file__).with_name("log_template.toml"))


def parse_log_line(raw: str, state: dict[str, object]) -> tuple[str, dict[str, object]]:
    """Strip the maa-cli envelope while retaining its structured metadata."""
    match = LOG_LINE_RE.match(raw)
    if state.get("json_capture"):
        _consume_json_fragment(match.group("body") if match is not None else raw, state)
        return "", {}
    if match is None:
        return raw, {}
    level = match.group("level")
    body = match.group("body")
    json_match = re.match(r"^(?:OperBox|Depot):\s*(\{.*)$", body)
    if json_match is not None:
        state.update({"json_capture": True, "json_depth": 0, "json_in_string": False, "json_escape": False})
        _consume_json_fragment(json_match.group(1), state)
        return "", {}
    return body, {
        "time": server_datetime_from_text(match.group("time")),
        "level": level,
        "tone": LEVEL_TONE.get(level, "default"),
        "enveloped": True,
    }


def _consume_json_fragment(text: str, state: dict[str, object]) -> None:
    depth = int(state.get("json_depth") or 0)
    in_string = bool(state.get("json_in_string"))
    escaped = bool(state.get("json_escape"))
    for char in text:
        if escaped:
            escaped = False
            continue
        if in_string:
            if char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
    if depth <= 0 and not in_string:
        state.clear()
        return
    state["json_depth"] = depth
    state["json_in_string"] = in_string
    state["json_escape"] = escaped
