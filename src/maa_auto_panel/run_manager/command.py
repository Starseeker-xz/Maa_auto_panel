from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandSpec:
    """Concrete subprocess inputs, independent from application runtime objects."""

    cmd: list[str]
    cwd: Path
    env: dict[str, str]
    output_log_file: Path | None = None
