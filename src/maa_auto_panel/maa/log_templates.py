from __future__ import annotations

import re
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from maa_auto_panel.diagnostics import get_logger
from maa_auto_panel.logs.pipeline import LogSourceSpec
from maa_auto_panel.logs.templates.loader import load_translation_template_tolerant
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
MAA_LOG_TEMPLATE_PATH = Path(__file__).with_name("log_template.toml")

logger = get_logger(__name__)
_template_lock = threading.Lock()
_last_good_template: TranslationTemplate | None = None


@dataclass(frozen=True)
class MaaTemplateSnapshot:
    template: TranslationTemplate | None
    user_message: str | None = None
    user_tone: str = "warning"


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
    log.pipeline.context["maa_log_state"] = state
    blocks_before = list(log.pipeline.block_definitions)
    context_before = dict(log.pipeline.context)
    try:
        snapshot = load_maa_translation_template()
        if snapshot.template is not None:
            runtime = TemplateBlockRuntime(snapshot.template, state, fallback_block="task")
            runtime.register(log.pipeline)
        if snapshot.user_message:
            log.pipeline.context["maa_log_template_error"] = snapshot.user_message
            append_template_error_event(log, snapshot.user_message, snapshot.user_tone)
    except Exception as exc:
        log.pipeline.block_definitions[:] = blocks_before
        log.pipeline.context.clear()
        log.pipeline.context.update(context_before)
        log.pipeline.context["maa_log_template_error"] = str(exc)
        logger.exception("MAA log template unavailable; using plain visible-log fallback path=%s", MAA_LOG_TEMPLATE_PATH)
        append_template_error_event(log, "日志模板加载失败，已切换到原始日志。", "warning")
    return state


def begin_maa_task_sequence(log: "RunLogBuffer", tasks: list[dict[str, str]]) -> None:
    state = log.pipeline.context.get("maa_log_state")
    if not isinstance(state, MaaLogState):
        raise RuntimeError("MAA log template must be configured before its task sequence")
    state.begin_task_sequence(tasks)


def maa_translation_template() -> TranslationTemplate:
    snapshot = load_maa_translation_template()
    if snapshot.template is None:
        raise RuntimeError("No usable MAA log template")
    return snapshot.template


def load_maa_translation_template() -> MaaTemplateSnapshot:
    """Read the TOML for each new log buffer so edits apply without a restart."""
    global _last_good_template
    with _template_lock:
        try:
            loaded = load_translation_template_tolerant(MAA_LOG_TEMPLATE_PATH)
        except Exception:
            if _last_good_template is not None:
                logger.exception(
                    "MAA log template could not be decoded; using last-known-good template path=%s",
                    MAA_LOG_TEMPLATE_PATH,
                )
                return MaaTemplateSnapshot(_last_good_template, "日志模板加载失败，已使用上一次有效模板。")
            logger.exception("MAA log template could not be decoded; using plain fallback path=%s", MAA_LOG_TEMPLATE_PATH)
            return MaaTemplateSnapshot(None, "日志模板加载失败，已切换到原始日志。")
        for diagnostic in loaded.diagnostics:
            logger.warning("MAA log template fragment ignored: %s", diagnostic)
        if loaded.template.blocks:
            _last_good_template = loaded.template
        elif _last_good_template is not None:
            logger.error(
                "MAA log template contains no usable blocks; using last-known-good template path=%s",
                MAA_LOG_TEMPLATE_PATH,
            )
            return MaaTemplateSnapshot(_last_good_template, "日志模板加载失败，已使用上一次有效模板。")
        return MaaTemplateSnapshot(
            loaded.template,
            "日志模板部分配置无效，已忽略错误项。" if loaded.diagnostics else None,
        )


def append_template_error_event(log: "RunLogBuffer", message: str, tone: str) -> None:
    try:
        log.pipeline.append(
            f"{message}\n",
            source="framework:event",
            metadata={
                "tone": tone,
                "kind_override": "event",
                "status_override": "warning",
                "message_metadata": {"event_key": "visible-log-template-error"},
            },
        )
    except Exception:
        logger.exception("MAA log template fallback event could not be appended")


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
