from __future__ import annotations

import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import tomli_w

from linux_maa.maa.runtime import MaaRuntime
from linux_maa.config.schema import ConfigSchemaValidator
from linux_maa.config.tasks import TASK_SUFFIXES, WRITABLE_TASK_SUFFIXES, inflate_managed_params_for_edit, task_items_to_config_data
from linux_maa.storage import TrashManager, TrashRecord
from linux_maa.utils import relative_path, resolve_existing_named_file, slugify, validate_file_name, write_text_atomic

CONFIG_KINDS = {
    "profiles": "profiles",
    "tasks": "tasks",
}
CONFIG_SUFFIXES = TASK_SUFFIXES


@dataclass(frozen=True)
class ConfigFile:
    kind: str
    name: str
    filename: str
    path: str
    suffix: str
    size: int
    modified_at: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ConfigValidationFailure(ValueError):
    def __init__(self, result: object) -> None:
        super().__init__("Config validation failed")
        self.result = result


class ConfigManager:
    """Single place for framework-managed maa-cli config files."""

    def __init__(self, runtime: MaaRuntime) -> None:
        self.runtime = runtime
        self.schema_validator = ConfigSchemaValidator(runtime)
        self.trash = TrashManager(runtime.config_dir / ".trash", repo_root=runtime.repo_root)

    def ensure_dirs(self) -> None:
        for dirname in CONFIG_KINDS.values():
            (self.runtime.config_dir / dirname).mkdir(parents=True, exist_ok=True)

    def list_all(self) -> dict[str, list[ConfigFile]]:
        self.ensure_dirs()
        return {kind: self.list_kind(kind) for kind in CONFIG_KINDS}

    def list_kind(self, kind: str) -> list[ConfigFile]:
        directory = self._kind_dir(kind)
        files: list[ConfigFile] = []
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            if not path.is_file() or path.suffix.lower() not in CONFIG_SUFFIXES:
                continue
            stat = path.stat()
            files.append(
                ConfigFile(
                    kind=kind,
                    name=path.stem,
                    filename=path.name,
                    path=relative_path(path, self.runtime.repo_root),
                    suffix=path.suffix.lower().lstrip("."),
                    size=stat.st_size,
                    modified_at=stat.st_mtime,
                )
            )
        return files

    def read(self, kind: str, name: str) -> tuple[ConfigFile, str]:
        path = self.resolve(kind, name)
        return self._read_path(kind, path)

    def _read_path(self, kind: str, path: Path) -> tuple[ConfigFile, str]:
        stat = path.stat()
        info = ConfigFile(
            kind=kind,
            name=path.stem,
            filename=path.name,
            path=relative_path(path, self.runtime.repo_root),
            suffix=path.suffix.lower().lstrip("."),
            size=stat.st_size,
            modified_at=stat.st_mtime,
        )
        return info, path.read_text(encoding="utf-8")

    def read_task_items(self, name: str) -> list[dict[str, object]]:
        data = self.read_structured("tasks", name)
        return self.task_items_from_data(data)

    def read_task_config(self, name: str) -> dict[str, object]:
        path = self.resolve("tasks", name)
        return self._task_config_response(path)

    def _task_config_response(self, path: Path) -> dict[str, object]:
        info, content = self._read_path("tasks", path)
        data = self._read_structured_path(path)
        return {
            "file": info.to_dict(),
            "content": content,
            "data": data,
            "task_items": self.task_items_from_data(data),
            "validation": self.schema_validator.validate_task_config(data).to_dict(),
            "metadata_schema": self.schema_validator.metadata_validator.schema,
        }

    def read_profile_config(self, name: str) -> dict[str, object]:
        path = self.resolve("profiles", name)
        info, content = self._read_path("profiles", path)
        data = self._read_structured_path(path)
        return {
            "file": info.to_dict(),
            "content": content,
            "data": data,
            "validation": self.schema_validator.validate_profile_config(data).to_dict(),
        }

    def read_cli_config(self) -> dict[str, object]:
        path = self.runtime.config_dir / "cli.toml"
        if path.exists():
            info, content = self._read_path("cli", path)
            data = self._read_structured_path(path)
        else:
            data = default_cli_config()
            content = ""
            info = ConfigFile(
                kind="cli",
                name="cli",
                filename="cli.toml",
                path=relative_path(path, self.runtime.repo_root),
                suffix="toml",
                size=0,
                modified_at=0,
            )
        return {
            "file": info.to_dict(),
            "content": content,
            "data": data,
            "validation": self.schema_validator.validate_cli_config(data).to_dict(),
        }

    def task_items_from_data(self, data: dict[str, object]) -> list[dict[str, object]]:
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            return []

        items: list[dict[str, object]] = []
        seen_ids: set[str] = set()
        for index, task in enumerate(tasks, start=1):
            if not isinstance(task, dict):
                continue
            name_value = task.get("name") or task.get("type") or f"Task {index}"
            type_value = task.get("type") or "Unknown"
            params = task.get("params") if isinstance(task.get("params"), dict) else {}
            enabled = params.get("enable") if isinstance(params.get("enable"), bool) else task.get("enabled", True)
            framework = task.get("linux_maa")
            framework_meta = dict(framework) if isinstance(framework, dict) else {}
            edit_params, framework_meta = inflate_managed_params_for_edit(str(type_value), dict(params), framework_meta)
            task_id = self._unique_task_item_id(self._task_item_id(task, str(type_value)), seen_ids)
            framework_meta["id"] = task_id
            items.append(
                {
                    "id": task_id,
                    "index": index,
                    "name": str(name_value),
                    "type": str(type_value),
                    "enabled": bool(enabled),
                    "strategy": task.get("strategy"),
                    "params": edit_params,
                    "variants": task.get("variants") if isinstance(task.get("variants"), list) else [],
                    "linux_maa": framework_meta,
                }
            )
        return items

    def read_structured(self, kind: str, name: str) -> dict[str, object]:
        path = self.resolve(kind, name)
        return self._read_structured_path(path)

    def _read_structured_path(self, path: Path) -> dict[str, object]:
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".toml":
            return tomllib.loads(content)
        if path.suffix.lower() == ".json":
            loaded = json.loads(content)
            if isinstance(loaded, dict):
                return loaded
            raise ValueError("Config JSON root must be an object")
        raise ValueError(f"Cannot parse {path.suffix} config yet")

    def write_task_config(
        self,
        name: str,
        *,
        base_data: dict[str, object],
        task_items: list[dict[str, object]],
    ) -> dict[str, object]:
        path = self.resolve_for_write("tasks", name, default_suffix=".toml")
        data = task_items_to_config_data(base_data, task_items)
        validation = self.schema_validator.validate_task_config(data)
        if not validation.valid:
            raise ConfigValidationFailure(validation)

        content = self._serialize(path.suffix.lower(), data)
        write_text_atomic(path, content)
        return self._task_config_response(path)

    def write_profile_config(self, name: str, data: dict[str, object]) -> dict[str, object]:
        validation = self.schema_validator.validate_profile_config(data)
        if not validation.valid:
            raise ConfigValidationFailure(validation)
        path = self.resolve_for_write("profiles", name, default_suffix=".toml")
        write_text_atomic(path, self._serialize(path.suffix.lower(), data))
        return self.read_profile_config(path.stem)

    def write_cli_config(self, data: dict[str, object]) -> dict[str, object]:
        validation = self.schema_validator.validate_cli_config(data)
        if not validation.valid:
            raise ConfigValidationFailure(validation)
        path = self.runtime.config_dir / "cli.toml"
        write_text_atomic(path, self._serialize(".toml", data))
        return self.read_cli_config()

    def delete(self, kind: str, name: str) -> TrashRecord:
        path = self.resolve(kind, name)
        return self.trash.move(path, label=f"{kind}:{path.name}")

    def _task_item_id(self, task: dict[str, object], task_type: str) -> str:
        framework = task.get("linux_maa")
        explicit_id = framework.get("id") if isinstance(framework, dict) else None

        if isinstance(explicit_id, str) and explicit_id.strip():
            return slugify(explicit_id) or "task"

        name = task.get("name")
        base_source = f"{task_type}-{name}" if isinstance(name, str) and name.strip() else task_type
        return slugify(base_source) or "task"

    def _unique_task_item_id(self, base_id: str, seen_ids: set[str]) -> str:
        if base_id not in seen_ids:
            seen_ids.add(base_id)
            return base_id

        suffix = 2
        while f"{base_id}-{suffix}" in seen_ids:
            suffix += 1
        task_id = f"{base_id}-{suffix}"
        seen_ids.add(task_id)
        return task_id

    def resolve(self, kind: str, name: str) -> Path:
        directory = self._kind_dir(kind)
        return resolve_existing_named_file(directory, name, suffixes=CONFIG_SUFFIXES, label="config name")

    def resolve_for_write(self, kind: str, name: str, *, default_suffix: str) -> Path:
        try:
            return self.resolve(kind, name)
        except FileNotFoundError:
            pass

        directory = self._kind_dir(kind)
        requested = validate_file_name(name, label="config name")

        suffix = requested.suffix.lower() or default_suffix
        if suffix not in WRITABLE_TASK_SUFFIXES:
            raise ValueError(f"Cannot write {suffix} config yet")

        stem = requested.stem if requested.suffix else requested.name
        if not slugify(stem):
            raise ValueError("Invalid config name")
        path = directory / f"{stem}{suffix}"
        try:
            path.relative_to(directory)
        except ValueError as exc:
            raise ValueError("Invalid config path") from exc
        return path

    def _serialize(self, suffix: str, data: dict[str, object]) -> str:
        if suffix == ".toml":
            return tomli_w.dumps(data)
        if suffix == ".json":
            return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        raise ValueError(f"Cannot write {suffix} config yet")

    def _kind_dir(self, kind: str) -> Path:
        dirname = CONFIG_KINDS.get(kind)
        if dirname is None:
            raise ValueError(f"Unsupported config kind: {kind}")
        path = self.runtime.config_dir / dirname
        path.mkdir(parents=True, exist_ok=True)
        return path


def default_cli_config() -> dict[str, object]:
    return {
        "$schema": "../../docs/maa-cli/schemas/cli.schema.json",
        "core": {
            "channel": "Stable",
            "test_time": 0,
            "components": {"library": True, "resource": True},
        },
        "cli": {
            "channel": "Stable",
            "components": {"binary": True},
        },
        "resource": {
            "auto_update": False,
            "warn_on_update_failure": True,
            "backend": "git",
            "remote": {
                "branch": "main",
                "url": "https://github.com/MaaAssistantArknights/MaaResource.git",
            },
        },
    }
