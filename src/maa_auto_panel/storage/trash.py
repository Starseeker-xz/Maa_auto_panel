from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from maa_auto_panel.time_utils import server_now, server_now_iso
from maa_auto_panel.storage.path_references import PathReferenceResolver


@dataclass(frozen=True)
class TrashRecord:
    """Immutable record of a file moved to trash: original path, trash path, timestamp, size, label."""
    original_path: str
    trash_path: str
    deleted_at: str
    size: int
    label: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class TrashManager:
    """Move files into a structured recycle folder with lightweight metadata."""

    def __init__(self, trash_root: Path, *, logical_root: Path, root_name: str = "data") -> None:
        self.trash_root = trash_root
        self.root_name = root_name
        self.references = PathReferenceResolver({root_name: logical_root})

    def move(self, source: Path, *, label: str = "") -> TrashRecord:
        source = source.resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        if not source.is_file():
            raise ValueError("Only files can be moved to trash")

        trash_root = self.trash_root.resolve()
        if trash_root == source or trash_root in source.parents:
            raise ValueError("Cannot move a trash entry into itself")

        deleted_at = server_now_iso()
        safe_time = server_now().strftime("%Y%m%d-%H%M%S")
        entry_dir = trash_root / f"{safe_time}-{source.stem}-{uuid.uuid4().hex[:8]}"
        target = entry_dir / self._relative_source_path(source)
        target.parent.mkdir(parents=True, exist_ok=True)

        size = source.stat().st_size
        shutil.move(str(source), str(target))

        record = TrashRecord(
            original_path=self.references.reference(self.root_name, source),
            trash_path=self.references.reference(self.root_name, target),
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
        try:
            return source.relative_to(self.references.resolve(f"{self.root_name}:.", expected_root=self.root_name))
        except ValueError:
            return Path(source.name)
