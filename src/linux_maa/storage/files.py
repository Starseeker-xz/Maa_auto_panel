from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from linux_maa.utils import write_text_atomic


def append_text(path: Path, text: str) -> None:
    """Append text string to file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(text)


def append_jsonl(path: Path, data: dict[str, object]) -> None:
    """Append JSON-serialized dict as a single JSONL line to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read and parse JSONL file; return list of dicts (skipping blank/malformed lines)."""
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def read_json_object(path: Path) -> dict[str, Any]:
    """Read JSON file as dict, or return empty dict on failure."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_json_object(path: Path, data: dict[str, Any]) -> None:
    """Atomically write dict as pretty-printed, sorted-key JSON file."""
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
