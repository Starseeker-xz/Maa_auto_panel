from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from linux_maa.maa.runtime import MaaRuntime
from linux_maa.utils import relative_path, validate_file_name


VARIABLE_RE = re.compile(r"^\s*#\s*linux-maa-var:\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\|\s*(?P<label>[^|]+)(?:\|\s*(?P<default>.*))?$")


@dataclass(frozen=True)
class ScriptVariable:
    name: str
    label: str
    default: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "label": self.label, "default": self.default}


@dataclass(frozen=True)
class ScriptInfo:
    name: str
    path: str
    variables: list[ScriptVariable]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": self.path,
            "variables": [variable.to_dict() for variable in self.variables],
        }


@dataclass(frozen=True)
class ScriptCommand:
    cmd: list[str]
    env: dict[str, str]


class ScheduleScriptManager:
    def __init__(self, runtime: MaaRuntime) -> None:
        self.runtime = runtime
        self.runtime.script_dir.mkdir(parents=True, exist_ok=True)

    def list_scripts(self) -> list[ScriptInfo]:
        return [self.inspect(path.name) for path in sorted(self.runtime.script_dir.iterdir(), key=lambda item: item.name) if path.is_file()]

    def inspect(self, name: str) -> ScriptInfo:
        path = self.resolve(name)
        return ScriptInfo(
            name=path.name,
            path=relative_path(path, self.runtime.repo_root),
            variables=parse_script_variables(path),
        )

    def command(self, name: str, variables: dict[str, str]) -> ScriptCommand:
        path = self.resolve(name)
        env = self.runtime.env()
        for variable in parse_script_variables(path):
            env[variable.name] = variables.get(variable.name, variable.default)
        return ScriptCommand(cmd=["/bin/sh", str(path)], env=env)

    def resolve(self, name: str) -> Path:
        requested = validate_file_name(name, label="script name")
        path = self.runtime.script_dir / requested.name
        try:
            path.relative_to(self.runtime.script_dir)
        except ValueError as exc:
            raise ValueError("Invalid script path") from exc
        if not path.is_file():
            raise FileNotFoundError(name)
        return path


def parse_script_variables(path: Path) -> list[ScriptVariable]:
    variables: list[ScriptVariable] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = VARIABLE_RE.match(line)
        if match is None:
            continue
        variables.append(
            ScriptVariable(
                name=match.group("name"),
                label=match.group("label").strip(),
                default=(match.group("default") or "").strip(),
            )
        )
    return variables
