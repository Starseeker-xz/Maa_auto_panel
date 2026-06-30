from __future__ import annotations

import json
import tomllib
from hashlib import sha1
from dataclasses import asdict, dataclass
from pathlib import Path
import re

from linux_maa.maa.runtime import MaaRuntime
from linux_maa.config.schema import ConfigSchemaValidator

CONFIG_KINDS = {
    "profiles": "profiles",
    "tasks": "tasks",
}
CONFIG_SUFFIXES = {".toml", ".json", ".yaml", ".yml"}


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


class ConfigManager:
    """Single place for framework-managed maa-cli config files."""

    def __init__(self, runtime: MaaRuntime) -> None:
        self.runtime = runtime
        self.schema_validator = ConfigSchemaValidator(runtime)

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
                    path=str(path.relative_to(self.runtime.repo_root)),
                    suffix=path.suffix.lower().lstrip("."),
                    size=stat.st_size,
                    modified_at=stat.st_mtime,
                )
            )
        return files

    def read(self, kind: str, name: str) -> tuple[ConfigFile, str]:
        path = self.resolve(kind, name)
        stat = path.stat()
        info = ConfigFile(
            kind=kind,
            name=path.stem,
            filename=path.name,
            path=str(path.relative_to(self.runtime.repo_root)),
            suffix=path.suffix.lower().lstrip("."),
            size=stat.st_size,
            modified_at=stat.st_mtime,
        )
        return info, path.read_text(encoding="utf-8")

    def read_task_items(self, name: str) -> list[dict[str, object]]:
        data = self.read_structured("tasks", name)
        return self.task_items_from_data(data)

    def read_task_config(self, name: str) -> dict[str, object]:
        info, content = self.read("tasks", name)
        data = self.read_structured("tasks", name)
        return {
            "file": info.to_dict(),
            "content": content,
            "data": data,
            "task_items": self.task_items_from_data(data),
            "validation": self.schema_validator.validate_task_config(data).to_dict(),
            "metadata_schema": self.schema_validator.metadata_validator.schema,
        }

    def task_items_from_data(self, data: dict[str, object]) -> list[dict[str, object]]:
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            return []

        items: list[dict[str, object]] = []
        seen_ids: dict[str, int] = {}
        for index, task in enumerate(tasks, start=1):
            if not isinstance(task, dict):
                continue
            name_value = task.get("name") or task.get("type") or f"Task {index}"
            type_value = task.get("type") or "Unknown"
            enabled = task.get("enabled", True)
            framework = task.get("linux_maa")
            framework_meta = framework if isinstance(framework, dict) else {}
            base_id = self._task_item_id(task, str(type_value))
            seen_count = seen_ids.get(base_id, 0) + 1
            seen_ids[base_id] = seen_count
            task_id = base_id if seen_count == 1 else f"{base_id}-{seen_count}"
            items.append(
                {
                    "id": task_id,
                    "index": index,
                    "name": str(name_value),
                    "type": str(type_value),
                    "enabled": bool(enabled),
                    "strategy": task.get("strategy"),
                    "params": task.get("params") if isinstance(task.get("params"), dict) else {},
                    "variants": task.get("variants") if isinstance(task.get("variants"), list) else [],
                    "linux_maa": framework_meta,
                }
            )
        return items

    def read_structured(self, kind: str, name: str) -> dict[str, object]:
        path = self.resolve(kind, name)
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".toml":
            return tomllib.loads(content)
        if path.suffix.lower() == ".json":
            loaded = json.loads(content)
            if isinstance(loaded, dict):
                return loaded
            raise ValueError("Config JSON root must be an object")
        raise ValueError(f"Cannot parse {path.suffix} config yet")

    def _task_item_id(self, task: dict[str, object], task_type: str) -> str:
        framework = task.get("linux_maa")
        explicit_id = framework.get("id") if isinstance(framework, dict) else None
        if isinstance(explicit_id, str) and explicit_id.strip():
            return self._slug(explicit_id)

        maa_task = {key: value for key, value in task.items() if key != "linux_maa"}
        serialized = json.dumps(maa_task, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        digest = sha1(serialized.encode("utf-8")).hexdigest()[:12]
        return f"{self._slug(task_type) or 'task'}-{digest}"

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-").lower()
        return slug[:64]

    def resolve(self, kind: str, name: str) -> Path:
        directory = self._kind_dir(kind)
        requested = Path(name)
        if requested.name != name or name in {"", ".", ".."}:
            raise ValueError("Invalid config name")

        candidates: list[Path]
        if requested.suffix:
            candidates = [directory / requested.name]
        else:
            candidates = [directory / f"{name}{suffix}" for suffix in sorted(CONFIG_SUFFIXES)]

        for candidate in candidates:
            try:
                candidate.relative_to(directory)
            except ValueError as exc:
                raise ValueError("Invalid config path") from exc
            if candidate.is_file() and candidate.suffix.lower() in CONFIG_SUFFIXES:
                return candidate
        raise FileNotFoundError(name)

    def _kind_dir(self, kind: str) -> Path:
        dirname = CONFIG_KINDS.get(kind)
        if dirname is None:
            raise ValueError(f"Unsupported config kind: {kind}")
        path = self.runtime.config_dir / dirname
        path.mkdir(parents=True, exist_ok=True)
        return path
