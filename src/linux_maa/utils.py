from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any


def slugify(value: str, *, max_length: int = 64) -> str:
    """Produce a URL/filesystem-safe slug from a string, lowercased and truncated."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-").lower()[:max_length]


def dict_value(value: object) -> dict[str, Any]:
    """Return value as dict if it is one, otherwise return empty dict."""
    return value if isinstance(value, dict) else {}


def write_text_atomic(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write text to path atomically via temp file + rename, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    temp_path.write_text(content, encoding=encoding)
    temp_path.replace(path)


def relative_path(path: Path, root: Path) -> str:
    """Return path as a string relative to root, or absolute if outside root."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def validate_file_name(name: str, *, label: str = "name") -> Path:
    """Validate a name is not absolute, empty, or path traversal; return as Path."""
    requested = Path(name)
    if requested.is_absolute() or requested.name != name or name in {"", ".", ".."}:
        raise ValueError(f"Invalid {label}")
    return requested


def resolve_existing_named_file(
    directory: Path,
    name: str,
    *,
    suffixes: tuple[str, ...],
    label: str = "file name",
) -> Path:
    """Find an existing file by name in directory, trying suffixes in order."""
    requested = validate_file_name(name, label=label)
    normalized_suffixes = tuple(suffix.lower() for suffix in suffixes)
    candidates = [directory / requested.name] if requested.suffix else [directory / f"{name}{suffix}" for suffix in normalized_suffixes]

    for candidate in candidates:
        try:
            candidate.relative_to(directory)
        except ValueError as exc:
            raise ValueError(f"Invalid {label.replace(' name', ' path')}") from exc
        if candidate.is_file() and candidate.suffix.lower() in normalized_suffixes:
            return candidate
    raise FileNotFoundError(name)


def bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    """Coerce value to int clamped between minimum and maximum, with a default on failure."""
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def extract_version(text: str) -> str:
    """Extract and normalize a version string (e.g. v6.13.0 -> 6.13.0) from text."""
    match = re.search(r"v?\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.-]+)?", text)
    return match.group(0).lstrip("v") if match else ""


def version_key(value: str) -> tuple[tuple[int, ...], str]:
    """Parse version into sortable (parts_tuple, suffix) for comparison."""
    cleaned = value.strip().lstrip("v")
    main, _, suffix = cleaned.partition("-")
    parts: list[int] = []
    for part in main.split("."):
        if not part.isdigit():
            break
        parts.append(int(part))
    return tuple(parts), suffix


def is_newer_version(current: str, latest: str) -> bool:
    """Return True if latest version string is newer than current version string."""
    if not current or not latest:
        return False
    current = current.removeprefix("v")
    latest = latest.removeprefix("v")
    if current == latest:
        return False
    return version_key(current) < version_key(latest)
