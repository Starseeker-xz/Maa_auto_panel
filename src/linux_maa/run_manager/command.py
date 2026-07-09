from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandSpec:
    """Concrete subprocess command, environment, and optional raw output file."""

    cmd: list[str]
    env: dict[str, str]
    output_log_file: Path | None = None
