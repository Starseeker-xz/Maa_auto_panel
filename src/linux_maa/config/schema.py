from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import cached_property
from typing import Any

from jsonschema import Draft7Validator

from linux_maa.maa.runner import strip_framework_task_metadata
from linux_maa.maa.runtime import MaaRuntime


LINUX_MAA_METADATA_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {
            "type": "string",
            "minLength": 1,
            "description": "Stable framework id for the task item.",
        },
        "unlimited_runs": {
            "type": "boolean",
            "default": True,
            "description": "Scheduled-run only. When true, ignore min_daily_successes and always run this task item.",
        },
        "min_daily_successes": {
            "type": "integer",
            "minimum": 0,
            "default": 1,
            "description": (
                "Scheduled-run only. If set to N, skip this task item after it has "
                "succeeded N times in the same day. 0 means the daily requirement is "
                "already satisfied and scheduled runs may skip it immediately. Ignored when unlimited_runs is true."
            ),
        },
        "important": {
            "type": "boolean",
            "default": False,
            "description": "Scheduled-run policy hint for future failure handling. Not enforced by the runner yet.",
        },
    },
}


@dataclass(frozen=True)
class ConfigValidationError:
    path: str
    message: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ConfigValidationResult:
    valid: bool
    errors: list[ConfigValidationError]

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "errors": [error.to_dict() for error in self.errors],
        }


class ConfigSchemaValidator:
    def __init__(self, runtime: MaaRuntime) -> None:
        self.runtime = runtime

    @cached_property
    def maa_task_schema(self) -> dict[str, Any]:
        schema_path = self.runtime.repo_root / "docs" / "maa-cli" / "schemas" / "task.schema.json"
        return json.loads(schema_path.read_text(encoding="utf-8"))

    @cached_property
    def maa_task_validator(self) -> Draft7Validator:
        return Draft7Validator(self.maa_task_schema)

    @cached_property
    def metadata_validator(self) -> Draft7Validator:
        return Draft7Validator(LINUX_MAA_METADATA_SCHEMA)

    def validate_task_config(self, data: dict[str, object]) -> ConfigValidationResult:
        errors: list[ConfigValidationError] = []
        sanitized = strip_framework_task_metadata(data)

        for error in sorted(self.maa_task_validator.iter_errors(sanitized), key=lambda item: list(item.path)):
            path = _format_json_path(error.path)
            errors.append(ConfigValidationError(path=path, message=error.message, source="maa-cli"))

        tasks = data.get("tasks")
        if isinstance(tasks, list):
            for index, task in enumerate(tasks):
                if not isinstance(task, dict):
                    continue
                metadata = task.get("linux_maa")
                if metadata is None:
                    continue
                if not isinstance(metadata, dict):
                    errors.append(
                        ConfigValidationError(
                            path=f"tasks[{index}].linux_maa",
                            message="linux_maa metadata must be an object",
                            source="linux-maa",
                        )
                    )
                    continue
                for error in sorted(self.metadata_validator.iter_errors(metadata), key=lambda item: list(item.path)):
                    errors.append(
                        ConfigValidationError(
                            path=_format_metadata_path(index, error.path),
                            message=error.message,
                            source="linux-maa",
                        )
                    )

        return ConfigValidationResult(valid=not errors, errors=errors)


def _format_metadata_path(index: int, parts: object) -> str:
    base = f"tasks[{index}].linux_maa"
    suffix = _format_json_path(parts, prefix="")
    return f"{base}.{suffix}" if suffix not in {"", "$"} else base


def _format_json_path(parts: object, *, prefix: str = "$") -> str:
    path = prefix
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path or "$"
