from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath


class PathReferenceResolver:
    """Encode persistent paths against named logical roots and resolve them safely."""

    def __init__(self, roots: Mapping[str, Path]) -> None:
        self._roots = {name: path.expanduser().resolve() for name, path in roots.items()}
        if not self._roots or any(not name or ":" in name for name in self._roots):
            raise ValueError("Logical path roots must have non-empty names without ':'")

    def reference(self, root: str, path: Path) -> str:
        base = self._root(root)
        resolved = path.expanduser().resolve()
        try:
            relative = resolved.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"Path escapes logical root {root!r}: {resolved}") from exc
        return f"{root}:{relative.as_posix()}"

    def resolve(self, reference: str, *, expected_root: str | None = None) -> Path:
        root, separator, raw_path = reference.partition(":")
        if not separator or not raw_path:
            raise ValueError(f"Invalid logical path reference: {reference!r}")
        if expected_root is not None and root != expected_root:
            raise ValueError(f"Expected logical root {expected_root!r}, got {root!r}")
        relative = PurePosixPath(raw_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Logical path escapes root {root!r}: {reference!r}")
        base = self._root(root)
        resolved = base.joinpath(*relative.parts).resolve()
        try:
            resolved.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"Logical path escapes root {root!r}: {reference!r}") from exc
        return resolved

    def _root(self, name: str) -> Path:
        try:
            return self._roots[name]
        except KeyError as exc:
            raise ValueError(f"Unknown logical path root: {name!r}") from exc
