from __future__ import annotations

import logging
import os
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from maa_auto_panel.paths import FrameworkPaths
from maa_auto_panel.storage.files import append_jsonl, append_text, read_jsonl
from maa_auto_panel.storage.path_references import PathReferenceResolver
from maa_auto_panel.time_utils import server_now_iso
from maa_auto_panel.utils import relative_path


LOGGER_NAME = "maa_auto_panel"


@dataclass(frozen=True)
class LogRetentionPolicy:
    max_age_days: int = 14
    max_event_log_files: int = 500
    max_stream_log_files_per_channel: int = 500
    max_incremental_log_files: int = 500
    max_framework_log_bytes: int = 20 * 1024 * 1024
    framework_log_backups: int = 5


@dataclass(frozen=True)
class IncrementalLogCapture:
    log_file: str | None
    next_offset: int
    captured_bytes: int


class Diagnostics:
    def __init__(
        self,
        paths: FrameworkPaths,
        references: PathReferenceResolver,
        retention: LogRetentionPolicy | None = None,
    ) -> None:
        self.paths = paths
        self.references = references
        self.retention = retention or LogRetentionPolicy()
        self._lock = threading.RLock()
        self.ensure_dirs()

    @property
    def framework_log_file(self) -> Path:
        return self.paths.framework_log_dir / "framework.log"

    @property
    def event_dir(self) -> Path:
        return self.paths.framework_event_log_dir

    @property
    def incremental_log_dir(self) -> Path:
        return self.paths.framework_external_log_dir / "incremental"

    def ensure_dirs(self) -> None:
        self.paths.framework_log_dir.mkdir(parents=True, exist_ok=True)
        self.event_dir.mkdir(parents=True, exist_ok=True)
        self.incremental_log_dir.mkdir(parents=True, exist_ok=True)

    def configure_logging(self) -> logging.Logger:
        return configure_framework_logging(self.paths, self.retention)

    def close_logging(self) -> None:
        logger = logging.getLogger(LOGGER_NAME)
        for handler in list(logger.handlers):
            if not getattr(handler, "_maa_auto_panel_framework_handler", False):
                continue
            try:
                handler.flush()
            finally:
                logger.removeHandler(handler)
                handler.close()

    def event_log_file(self, run_id: str) -> str:
        path = self._event_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        return self.references.reference("framework", path)

    def append_run_event(self, run_id: str, kind: str, source: str, text: str, **extra: object) -> None:
        if not text:
            return
        entry = {
            "time": _now(),
            "run_id": run_id,
            "kind": kind,
            "source": source,
            "text": text,
            **{key: value for key, value in extra.items() if value is not None},
        }
        with self._lock:
            append_jsonl(self._event_path(run_id), entry)

    def run_events(self, run_id: str, *, limit: int = 1000) -> list[dict[str, object]]:
        rows = read_jsonl(self._event_path(run_id))
        return rows[-limit:] if limit > 0 else rows

    def stream_log_files(self, channel: str, run_id: str, *, key_prefix: str = "") -> dict[str, str]:
        files = {
            f"{key_prefix}stdout": self._stream_path(channel, run_id, "stdout"),
            f"{key_prefix}stderr": self._stream_path(channel, run_id, "stderr"),
        }
        for path in files.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        return {key: self.references.reference("framework", path) for key, path in files.items()}

    def append_stream_output(self, channel: str, run_id: str, stream: str, text: str) -> None:
        if not text:
            return
        stream = "stderr" if stream == "stderr" else "stdout"
        with self._lock:
            append_text(self._stream_path(channel, run_id, stream), text)

    def stream_sink(self, channel: str) -> Callable[[str, str, str], None]:
        """Bind an opaque diagnostic channel for a RunLogProfile sink."""
        self._stream_path(channel, "probe", "stdout")
        return lambda run_id, stream, text: self.append_stream_output(channel, run_id, stream, text)

    def capture_file_increment(self, source: Path, start_offset: int, *, capture_id: str) -> IncrementalLogCapture:
        """Copy bytes appended to ``source`` into a framework-owned diagnostic log."""
        if not capture_id or Path(capture_id).name != capture_id or capture_id in {".", ".."}:
            raise ValueError("capture_id must be a non-empty file name")
        try:
            handle = source.open("rb")
        except FileNotFoundError:
            return IncrementalLogCapture(log_file=None, next_offset=0, captured_bytes=0)
        with handle:
            size = os.fstat(handle.fileno()).st_size
            offset = start_offset if 0 <= start_offset <= size else 0
            handle.seek(offset)
            content = handle.read()
            next_offset = handle.tell()
        if not content:
            return IncrementalLogCapture(log_file=None, next_offset=next_offset, captured_bytes=0)
        target = self.incremental_log_dir / f"{capture_id}.log"
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            _write_bytes_atomic(target, content)
        return IncrementalLogCapture(
            log_file=self.references.reference("framework", target),
            next_offset=next_offset,
            captured_bytes=len(content),
        )

    def enforce_retention(self, *, protected_paths: set[Path] | None = None) -> None:
        protected = protected_paths or set()
        # When the run store supplies ownership, every unreferenced run artifact
        # is an orphan and can be removed immediately. Standalone diagnostics
        # keeps the legacy age/count policy for callers without a run store.
        orphan_limit = 0 if protected_paths is not None else None
        with self._lock:
            cutoff = datetime.now() - timedelta(days=max(0, self.retention.max_age_days))
            _prune_files(
                self.event_dir,
                max_count=self.retention.max_event_log_files if orphan_limit is None else orphan_limit,
                cutoff=cutoff,
                protected=protected,
            )
            for directory in self._stream_log_dirs():
                _prune_files(
                    directory,
                    max_count=self.retention.max_stream_log_files_per_channel if orphan_limit is None else orphan_limit,
                    cutoff=cutoff,
                    protected=protected,
                )
            _prune_files(
                self.incremental_log_dir,
                max_count=self.retention.max_incremental_log_files if orphan_limit is None else orphan_limit,
                cutoff=cutoff,
                protected=protected,
            )

    def _event_path(self, run_id: str) -> Path:
        return self.event_dir / f"{run_id}.jsonl"

    def _stream_path(self, channel: str, run_id: str, stream: str) -> Path:
        if not channel or Path(channel).name != channel or channel in {".", "..", "incremental"}:
            raise ValueError("channel must be a non-empty diagnostic stream name")
        return self.paths.framework_external_log_dir / channel / f"{run_id}.{stream}.log"

    def _stream_log_dirs(self) -> list[Path]:
        root = self.paths.framework_external_log_dir
        if not root.exists():
            return []
        return [path for path in root.iterdir() if path.is_dir() and path != self.incremental_log_dir]

def configure_framework_logging(paths: FrameworkPaths, retention: LogRetentionPolicy | None = None) -> logging.Logger:
    policy = retention or LogRetentionPolicy()
    paths.framework_log_dir.mkdir(parents=True, exist_ok=True)
    log_file = paths.framework_log_dir / "framework.log"
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, "_maa_auto_panel_framework_handler", False):
            logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        log_file,
        maxBytes=policy.max_framework_log_bytes,
        backupCount=policy.framework_log_backups,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d %(levelname)-8s [%(process)d:%(threadName)s] %(name)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler._maa_auto_panel_framework_handler = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.debug("framework logging configured path=%s", relative_path(log_file, paths.root))
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def _prune_files(directory: Path, *, max_count: int, cutoff: datetime, protected: set[Path] | None = None) -> None:
    if not directory.exists():
        return
    protected = protected or set()
    files = [path for path in directory.rglob("*") if path.is_file() and path not in protected]
    expired = {path for path in files if _mtime(path) < cutoff}
    newest = sorted(files, key=_mtime, reverse=True)
    overflow = set(newest[max(0, max_count):]) if max_count > 0 else set(files)
    for path in sorted(expired | overflow, key=lambda item: str(item)):
        _unlink(path)


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)


def _now() -> str:
    return server_now_iso()


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
