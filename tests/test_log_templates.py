from __future__ import annotations

from pathlib import Path

import pytest

from maa_auto_panel.logs.templates.engine import TranslationEngine
from maa_auto_panel.logs.templates.loader import load_translation_template
from maa_auto_panel.logs.templates.model import MissingFieldsRequest, TemplateValidationError


def write_template(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "log-template.toml"
    path.write_text(content, encoding="utf-8")
    return path


class TaskMonitor:
    def __init__(self) -> None:
        self.name = "剿灭"

    def resolve_missing_fields(self, request: MissingFieldsRequest) -> dict[str, object]:
        return {"task.name": self.name} if "task.name" in request.missing_fields else {}


def test_translates_placeholder_styles_lookup_and_replacements(tmp_path: Path) -> None:
    path = write_template(
        tmp_path,
        """
version = 1

[global.lookups.product]
PureGold = "赤金"

[[blocks.task.rules]]
match = "ProductOfFacility: {product:text}"
text = "设施产物: {product}"
indent = 1
lookups = { product = "product" }
styles = { product = { tone = "theme", strong = true } }
""",
    )
    engine = TranslationEngine(load_translation_template(path))

    result = engine.translate("maa-cli:stderr", "ProductOfFacility: PureGold", block="task")

    assert result.matched is True
    assert result.message is not None
    assert result.message.text == "设施产物: 赤金"
    assert result.message.indent == 1
    assert result.message.segments == [
        {"text": "设施产物: "},
        {"text": "赤金", "tone": "theme", "strong": True},
    ]


def test_global_exact_translation_is_shared_and_rules_use_generated_locations(tmp_path: Path) -> None:
    path = write_template(
        tmp_path,
        """
version = 1

[global.translations]
Connected = "已连接"

[[blocks.task.rules]]
match = "Hello {name:word}"
text = "你好 {name}"

[blocks.summary]
""",
    )
    engine = TranslationEngine(load_translation_template(path))

    task_exact = engine.translate("maa-cli:stderr", "Connected", block="task")
    summary_exact = engine.translate("maa-cli:stdout", "Connected", block="summary")
    patterned = engine.translate("maa-cli:stderr", "Hello Doctor", block="task")

    assert task_exact.message is not None and task_exact.message.text == "已连接"
    assert summary_exact.message is not None and summary_exact.message.text == "已连接"
    assert task_exact.rule_location == "global.translations.Connected"
    assert patterned.rule_location == "blocks.task.rules[0]"


def test_monitor_can_patch_only_declared_dynamic_fields(tmp_path: Path) -> None:
    path = write_template(
        tmp_path,
        """
version = 1

[global.fields."task.name"]
type = "string"
external = true
fallback = "{source_name}"

[[blocks.task.rules]]
match = "{source_name:word} Start"
text = "任务 {task.name}"
""",
    )
    engine = TranslationEngine(load_translation_template(path), TaskMonitor())

    result = engine.translate("maa-cli:stderr", "Fight Start", block="task")

    assert result.message is not None
    assert result.message.text == "任务 剿灭"
    assert engine.diagnostics == []


def test_unresolved_dynamic_field_uses_declared_fallback(tmp_path: Path) -> None:
    path = write_template(
        tmp_path,
        """
version = 1

[global.fields."task.name"]
external = true
fallback = "{source_name}"

[[blocks.task.rules]]
match = "{source_name:word} Start"
text = "任务 {task.name}"
""",
    )
    engine = TranslationEngine(load_translation_template(path))

    result = engine.translate("maa-cli:stderr", "Fight Start", block="task")

    assert result.message is not None
    assert result.message.text == "任务 Fight"


def test_fold_emits_once_until_non_member_line(tmp_path: Path) -> None:
    path = write_template(
        tmp_path,
        """
version = 1

[global]

[[blocks.task.rules]]
match = "ReportTo{platform:word}: {url:text}"
action = "drop"
fold_group = "report"
fold_role = "noise"

[[blocks.task.rules]]
match = "Successfully ReportTo{platform:word}"
text = "汇报成功"
tone = "success"
fold_group = "report"
fold_role = "emit_once"
""",
    )
    engine = TranslationEngine(load_translation_template(path))
    state: dict[str, object] = {}

    lines = [
        "ReportToPenguinStats: https://example.test/a",
        "Successfully ReportToPenguinStats",
        "ReportToYituliu: https://example.test/b",
        "Successfully ReportToYituliu",
    ]
    messages = [
        engine.translate("maa-cli:stderr", line, block="task", fold_state=state).message
        for line in lines
    ]
    assert [message.text for message in messages if message is not None] == ["汇报成功"]

    engine.translate("maa-cli:stderr", "Current sanity: 1/210", block="task", fold_state=state)
    message = engine.translate(
        "maa-cli:stderr",
        "Successfully ReportToPenguinStats",
        block="task",
        fold_state=state,
    ).message
    assert message is not None
    assert message.text == "汇报成功"


def test_validates_unknown_output_field(tmp_path: Path) -> None:
    path = write_template(
        tmp_path,
        """
version = 1

[global]

[[blocks.default.rules]]
match = "Hello"
text = "{missing}"
""",
    )

    with pytest.raises(TemplateValidationError, match="unknown field: missing"):
        load_translation_template(path)


def test_rejects_manual_rule_ids(tmp_path: Path) -> None:
    path = write_template(
        tmp_path,
        """
version = 1

[global]

[[blocks.line.rules]]
id = "unnecessary"
match = "Hello"
text = "你好"
""",
    )

    with pytest.raises(TemplateValidationError, match=r"blocks\.line\.rules\[0\]\.id: unknown field"):
        load_translation_template(path)


def test_matches_declarative_block_end(tmp_path: Path) -> None:
    path = write_template(
        tmp_path,
        """
version = 1

[global]

[[blocks.task.end]]
source = "maa-cli:stderr"
match = "{source_name:word} Completed"
values = { status = "succeeded" }
""",
    )
    engine = TranslationEngine(load_translation_template(path))

    boundary = engine.match_end("task", "maa-cli:stderr", "Fight Completed")

    assert boundary is not None
    assert boundary.captures == {"source_name": "Fight"}
    assert boundary.values == {"status": "succeeded"}
