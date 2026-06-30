from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class TrashRecord:
    original_path: str
    trash_path: str
    deleted_at: str
    size: int
    label: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class TrashManager:
    """Move files into a structured recycle folder with lightweight metadata."""

    def __init__(self, trash_root: Path, *, repo_root: Path | None = None) -> None:
        self.trash_root = trash_root
        self.repo_root = repo_root

    def move(self, source: Path, *, label: str = "") -> TrashRecord:
        source = source.resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        if not source.is_file():
            raise ValueError("Only files can be moved to trash")

        trash_root = self.trash_root.resolve()
        if trash_root == source or trash_root in source.parents:
            raise ValueError("Cannot move a trash entry into itself")

        deleted_at = datetime.now().isoformat(timespec="seconds")
        safe_time = datetime.now().strftime("%Y%m%d-%H%M%S")
        entry_dir = trash_root / f"{safe_time}-{source.stem}-{uuid.uuid4().hex[:8]}"
        target = entry_dir / self._relative_source_path(source)
        target.parent.mkdir(parents=True, exist_ok=True)

        size = source.stat().st_size
        shutil.move(str(source), str(target))

        record = TrashRecord(
            original_path=self._display_path(source),
            trash_path=self._display_path(target),
            deleted_at=deleted_at,
            size=size,
            label=label,
        )
        (entry_dir / "trash-record.json").write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return record

    def _relative_source_path(self, source: Path) -> Path:
        if self.repo_root is None:
            return Path(source.name)
        try:
            return source.relative_to(self.repo_root.resolve())
        except ValueError:
            return Path(source.name)

    def _display_path(self, path: Path) -> str:
        if self.repo_root is None:
            return str(path)
        try:
            return str(path.relative_to(self.repo_root.resolve()))
        except ValueError:
            return str(path)
