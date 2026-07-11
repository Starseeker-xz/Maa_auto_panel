from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.state import RunKind
from maa_auto_panel.storage.files import read_json_object, write_json_object
from maa_auto_panel.time_utils import server_now_iso
from maa_auto_panel.utils import relative_path, slugify


@dataclass(frozen=True)
class StateRetentionPolicy:
    max_run_records: int = 500
    max_retry_records: int = 2000


@dataclass(frozen=True)
class StoredRun:
    id: str
    kind: RunKind
    status: str
    title: str
    started_at: str
    updated_at: str | None = None
    ended_at: str | None = None
    return_code: int | None = None
    max_retries: int = 1
    retry_count: int = 0
    retry_group_count: int = 0
    log_files: dict[str, str] = field(default_factory=dict)
    event_log_file: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    history_scope: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "title": self.title,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "ended_at": self.ended_at,
            "return_code": self.return_code,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "retry_group_count": self.retry_group_count,
            "log_files": dict(self.log_files),
            "event_log_file": self.event_log_file,
            "metadata": dict(self.metadata),
            "artifacts": dict(self.artifacts),
            "history_scope": list(self.history_scope),
        }
        return data


class RunStateStore:
    def __init__(self, runtime: MaaRuntime, retention: StateRetentionPolicy | None = None) -> None:
        self.runtime = runtime
        self.retention = retention or StateRetentionPolicy()
        self._lock = threading.RLock()
        self.ensure_dirs()

    @property
    def run_records_path(self) -> Path:
        return self.runtime.run_state_dir / "recent-run-records.json"

    @property
    def retries_path(self) -> Path:
        return self.runtime.run_state_dir / "run-retries.json"

    def ensure_dirs(self) -> None:
        self.runtime.run_state_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.run_history_dir.mkdir(parents=True, exist_ok=True)

    def enforce_retention(self) -> None:
        with self._lock:
            self._write_runs(self.runs(limit=0))
            retries = self._retry_items()[-self.retention.max_retry_records :]
            self._write_retries(retries)

    def recover_interrupted_runs(self) -> int:
        recovered = 0
        for item in self._run_items():
            run_id = str(item.get("id") or "")
            if not run_id or item.get("status") not in {"running", "stopping"}:
                continue
            metadata = dict(item.get("metadata")) if isinstance(item.get("metadata"), dict) else {}
            summary = dict(metadata.get("summary")) if isinstance(metadata.get("summary"), dict) else {}
            summary["recovered_status"] = str(item.get("status") or "running")
            summary["recovered_reason"] = "backend restarted before run finalized"
            metadata["summary"] = summary
            self._upsert_run({"id": run_id, "status": "stopped", "ended_at": _now(), "updated_at": _now(), "metadata": metadata})
            self._sync_run_history(run_id)
            recovered += 1
        return recovered

    def create_run(
        self,
        *,
        run_id: str,
        kind: RunKind,
        title: str,
        max_retries: int = 1,
        log_files: dict[str, str] | None = None,
        event_log_file: str | None = None,
        metadata: dict[str, Any] | None = None,
        artifacts: dict[str, Any] | None = None,
        history_scope: tuple[str, ...] = (),
    ) -> None:
        started_at = _now()
        data: dict[str, object] = {
            "id": run_id,
            "kind": kind,
            "status": "running",
            "title": title,
            "started_at": started_at,
            "updated_at": started_at,
            "max_retries": max(1, max_retries),
            "log_files": log_files or {},
            "event_log_file": event_log_file,
            "metadata": metadata or {},
            "artifacts": artifacts or {},
            "history_scope": list(history_scope),
        }
        self._upsert_run(data)

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        return_code: int | None = None,
        retry_count: int | None = None,
        retry_group_count: int | None = None,
        metadata: dict[str, Any] | None = None,
        artifacts: dict[str, Any] | None = None,
    ) -> None:
        patch: dict[str, object] = {
            "id": run_id,
            "status": status,
            "ended_at": _now(),
            "updated_at": _now(),
            "return_code": return_code,
        }
        if retry_count is not None:
            patch["retry_count"] = retry_count
        if retry_group_count is not None:
            patch["retry_group_count"] = retry_group_count
        if metadata is not None:
            patch["metadata"] = metadata
        if artifacts is not None:
            patch["artifacts"] = artifacts
        self._upsert_run(patch)
        self._sync_run_history(run_id)

    def add_retry(
        self,
        *,
        retry_id: str,
        run_id: str,
        retry_index: int,
        retry_group: int,
        status: str,
        started_at: str,
        updated_at: str,
        ended_at: str,
        return_code: int | None,
        metadata: dict[str, Any],
        artifacts: dict[str, Any],
        log_entries: list[dict[str, Any]],
        log_files: dict[str, str] | None = None,
    ) -> None:
        with self._lock:
            history_file = self._write_retry_history(
                run_id=run_id,
                retry_id=retry_id,
                retry_index=retry_index,
                retry_group=retry_group,
                status=status,
                started_at=started_at,
                updated_at=updated_at,
                ended_at=ended_at,
                return_code=return_code,
                metadata=metadata,
                artifacts=artifacts,
                log_entries=log_entries,
                log_files=log_files,
            )
            retries = [item for item in self._retry_items() if item.get("id") != retry_id]
            retries.append(
                {
                    "id": retry_id,
                    "run_id": run_id,
                    "retry_index": retry_index,
                    "retry_group": retry_group,
                    "status": status,
                    "started_at": started_at,
                    "updated_at": updated_at,
                    "ended_at": ended_at,
                    "return_code": return_code,
                    "metadata": metadata,
                    "artifacts": artifacts,
                    "log_entries_file": history_file,
                    "log_files": log_files or {},
                }
            )
            self._write_retries(retries[-self.retention.max_retry_records :])

    def runs(self, kind: RunKind | None = None, *, limit: int = 50) -> list[StoredRun]:
        records = [_stored_run_from_data(item) for item in self._run_items()]
        runs = [record for record in records if record is not None]
        if kind is not None:
            runs = [record for record in runs if record.kind == kind]
        runs.sort(key=lambda run: run.started_at, reverse=True)
        return runs if limit <= 0 else runs[:limit]

    def run(self, run_id: str) -> StoredRun | None:
        for item in self._run_items():
            if item.get("id") == run_id:
                return _stored_run_from_data(item)
        return None

    def delete_run(self, run_id: str) -> dict[str, object]:
        with self._lock:
            run = self.run(run_id)
            if run is None:
                raise KeyError(run_id)
            runs = [_stored_run_from_data(item) for item in self._run_items() if item.get("id") != run_id]
            retries = [item for item in self._retry_items() if item.get("run_id") != run_id]
            history_path = self._run_history_path(run_id, run)
            history_deleted = False
            if history_path.exists():
                history_path.unlink()
                history_deleted = True
            self._write_runs(runs)
            self._write_retries(retries)
            return {
                "id": run_id,
                "history_deleted": history_deleted,
                "history_path": relative_path(history_path, self.runtime.data_root),
            }

    def retries(self, run_id: str) -> list[dict[str, object]]:
        rows = [item for item in self._retry_items() if item.get("run_id") == run_id]
        rows.sort(key=lambda item: _int_value(item.get("retry_index")))
        return [self._retry_with_history(row) for row in rows]

    def _upsert_run(self, patch: dict[str, object]) -> None:
        with self._lock:
            run_id = str(patch.get("id") or "")
            if not run_id:
                raise ValueError("run id is required")
            by_id = {str(item.get("id") or ""): item for item in self._run_items() if item.get("id")}
            data = dict(by_id.get(run_id) or {})
            if isinstance(patch.get("metadata"), dict) and isinstance(data.get("metadata"), dict):
                patch_metadata = patch["metadata"]
                data_metadata = data["metadata"]
                if isinstance(patch_metadata, dict) and isinstance(data_metadata, dict):
                    patch = {**patch, "metadata": {**data_metadata, **patch_metadata}}
            if isinstance(patch.get("artifacts"), dict) and isinstance(data.get("artifacts"), dict):
                patch_artifacts = patch["artifacts"]
                data_artifacts = data["artifacts"]
                if isinstance(patch_artifacts, dict) and isinstance(data_artifacts, dict):
                    patch = {**patch, "artifacts": {**data_artifacts, **patch_artifacts}}
            data.update(patch)
            data.setdefault("started_at", _now())
            data.setdefault("updated_at", data["started_at"])
            data.setdefault("title", run_id)
            data.setdefault("kind", "manual")
            data.setdefault("metadata", {})
            data.setdefault("artifacts", {})
            data.setdefault("history_scope", [])
            by_id[run_id] = data
            self._write_runs([_stored_run_from_data(item) for item in by_id.values()])

    def _run_items(self) -> list[dict[str, object]]:
        data = read_json_object(self.run_records_path)
        runs = data.get("runs")
        return [item for item in runs if isinstance(item, dict)] if isinstance(runs, list) else []

    def _retry_items(self) -> list[dict[str, object]]:
        data = read_json_object(self.retries_path)
        retries = data.get("retries")
        return [item for item in retries if isinstance(item, dict)] if isinstance(retries, list) else []

    def _write_retry_history(
        self,
        *,
        run_id: str,
        retry_id: str,
        retry_index: int,
        retry_group: int,
        status: str,
        started_at: str,
        updated_at: str,
        ended_at: str,
        return_code: int | None,
        metadata: dict[str, Any],
        artifacts: dict[str, Any],
        log_entries: list[dict[str, Any]],
        log_files: dict[str, str] | None,
    ) -> str:
        run = self.run(run_id)
        path = self._run_history_path(run_id, run)
        existing = read_json_object(path)
        retries = [item for item in existing.get("retries", []) if isinstance(item, dict)]
        retries = [item for item in retries if item.get("id") != retry_id]
        retries.append(
            {
                "id": retry_id,
                "run_id": run_id,
                "retry_index": retry_index,
                "retry_group": retry_group,
                "status": status,
                "started_at": started_at,
                "updated_at": updated_at,
                "ended_at": ended_at,
                "return_code": return_code,
                "metadata": metadata,
                "artifacts": artifacts,
                "log_entries": log_entries,
                "log_files": log_files or {},
                "closed": True,
            }
        )
        retries.sort(key=lambda item: _int_value(item.get("retry_index")))
        data: dict[str, object] = {
            "description": "Durable run history with retry-scoped visible log blocks.",
            "updated_at": _now(),
            "run": run.to_dict() if run is not None else {"id": run_id},
            "retries": retries,
        }
        write_json_object(path, data)
        return relative_path(path, self.runtime.data_root)

    def _sync_run_history(self, run_id: str) -> None:
        run = self.run(run_id)
        if run is None:
            return
        path = self._run_history_path(run_id, run)
        existing = read_json_object(path)
        if not existing:
            return
        existing["description"] = existing.get("description") or "Durable run history with retry-scoped visible log blocks."
        existing["updated_at"] = _now()
        existing["run"] = run.to_dict()
        write_json_object(path, existing)

    def _retry_with_history(self, row: dict[str, object]) -> dict[str, object]:
        output = dict(row)
        if "log_entries" in output:
            return output
        history_file = output.get("log_entries_file")
        if not isinstance(history_file, str) or not history_file:
            output["log_entries"] = []
            return output
        path = self.runtime.data_root / history_file
        data = read_json_object(path)
        retry_id = output.get("id")
        for item in data.get("retries", []):
            if isinstance(item, dict) and item.get("id") == retry_id:
                output["log_entries"] = item.get("log_entries") if isinstance(item.get("log_entries"), list) else []
                return output
        output["log_entries"] = []
        return output

    def _run_history_path(self, run_id: str, run: StoredRun | None) -> Path:
        if run is None:
            return self.runtime.run_history_dir / "unknown" / f"{run_id}.json"
        scope = run.history_scope or ("unknown",)
        return self.runtime.run_history_dir.joinpath(*(_safe_path_part(part) for part in scope), f"{run_id}.json")

    def _write_runs(self, runs: list[StoredRun | None]) -> None:
        records = [run for run in runs if run is not None]
        records.sort(key=lambda run: run.started_at, reverse=True)
        data = {
            "description": "Recent WebUI, scheduled, maintenance, and tool run records. The WebUI derives recent runs from this file.",
            "updated_at": _now(),
            "runs": [run.to_dict() for run in records[: self.retention.max_run_records]],
        }
        write_json_object(self.run_records_path, data)

    def _write_retries(self, retries: list[dict[str, object]]) -> None:
        data = {
            "description": "Per-retry run index. Log blocks are stored in history/framework/runs and referenced by log_entries_file.",
            "updated_at": _now(),
            "retries": retries,
        }
        write_json_object(self.retries_path, data)


def _stored_run_from_data(data: dict[str, object]) -> StoredRun | None:
    run_id = str(data.get("id") or "")
    kind = str(data.get("kind") or "manual")
    if not run_id:
        return None
    log_files = data.get("log_files")
    metadata = data.get("metadata")
    artifacts = data.get("artifacts")
    history_scope = data.get("history_scope")
    return StoredRun(
        id=run_id,
        kind=kind,
        status=str(data.get("status") or "unknown"),
        title=str(data.get("title") or run_id),
        started_at=str(data.get("started_at") or ""),
        updated_at=_optional_str(data.get("updated_at")),
        ended_at=_optional_str(data.get("ended_at")),
        return_code=_optional_int(data.get("return_code")),
        max_retries=max(1, _int_value(data.get("max_retries")) or 1),
        retry_count=_int_value(data.get("retry_count")),
        retry_group_count=_int_value(data.get("retry_group_count")),
        log_files={str(key): str(value) for key, value in log_files.items()} if isinstance(log_files, dict) else {},
        event_log_file=_optional_str(data.get("event_log_file")),
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
        artifacts=dict(artifacts) if isinstance(artifacts, dict) else {},
        history_scope=tuple(str(item) for item in history_scope) if isinstance(history_scope, list) else (),
    )


def _now() -> str:
    return server_now_iso()


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_path_part(value: str) -> str:
    return slugify(value) or "unknown"
