from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from maa_auto_panel.storage.files import append_jsonl, append_text, read_jsonl
from maa_auto_panel.time_utils import server_now_iso
from maa_auto_panel.utils import relative_path, write_text_atomic

if TYPE_CHECKING:
    from maa_auto_panel.maa.runtime import MaaRuntime


LOGGER_NAME = "maa_auto_panel"


@dataclass(frozen=True)
class LogRetentionPolicy:
    max_age_days: int = 14
    max_event_log_files: int = 500
    max_maa_cli_log_files: int = 500
    max_tool_log_files: int = 500
    max_script_log_files: int = 500
    max_maacore_capture_files: int = 500
    max_generated_config_dirs: int = 200
    max_legacy_run_log_files: int = 200
    max_maacore_debug_files: int = 500
    max_asst_log_bytes: int = 50 * 1024 * 1024
    max_framework_log_bytes: int = 20 * 1024 * 1024
    framework_log_backups: int = 5


class Diagnostics:
    def __init__(self, runtime: MaaRuntime, retention: LogRetentionPolicy | None = None) -> None:
        self.runtime = runtime
        self.retention = retention or LogRetentionPolicy()
        self._lock = threading.RLock()
        self.ensure_dirs()

    @property
    def framework_log_file(self) -> Path:
        return self.runtime.framework_log_dir / "framework.log"

    @property
    def event_dir(self) -> Path:
        return self.runtime.framework_event_log_dir

    @property
    def maa_cli_log_dir(self) -> Path:
        return self.runtime.maa_cli_log_dir

    @property
    def tool_log_dir(self) -> Path:
        return self.runtime.framework_external_log_dir / "tools"

    @property
    def script_log_dir(self) -> Path:
        return self.runtime.framework_external_log_dir / "scripts"

    @property
    def maacore_log_dir(self) -> Path:
        return self.runtime.maacore_capture_log_dir

    def ensure_dirs(self) -> None:
        self.runtime.framework_log_dir.mkdir(parents=True, exist_ok=True)
        self.event_dir.mkdir(parents=True, exist_ok=True)
        self.maa_cli_log_dir.mkdir(parents=True, exist_ok=True)
        self.tool_log_dir.mkdir(parents=True, exist_ok=True)
        self.script_log_dir.mkdir(parents=True, exist_ok=True)
        self.maacore_log_dir.mkdir(parents=True, exist_ok=True)

    def configure_logging(self) -> logging.Logger:
        return configure_framework_logging(self.runtime, self.retention)

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
        return relative_path(path, self.runtime.data_root)

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

    def maa_cli_log_file(self, run_id: str) -> str:
        return self.maa_cli_log_files(run_id)["stdout"]

    def maa_cli_log_files(self, run_id: str) -> dict[str, str]:
        files = {
            "stdout": self._maa_cli_path(run_id, "stdout"),
            "stderr": self._maa_cli_path(run_id, "stderr"),
        }
        for path in files.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        return {key: relative_path(path, self.runtime.data_root) for key, path in files.items()}

    def append_maa_cli_output(self, run_id: str, stream: str, text: str) -> None:
        if not text:
            return
        stream = "stderr" if stream == "stderr" else "stdout"
        with self._lock:
            append_text(self._maa_cli_path(run_id, stream), text)

    def tool_log_file(self, run_id: str) -> str:
        return self.tool_log_files(run_id)["stdout"]

    def tool_log_files(self, run_id: str) -> dict[str, str]:
        files = {
            "stdout": self._tool_path(run_id, "stdout"),
            "stderr": self._tool_path(run_id, "stderr"),
        }
        for path in files.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        return {key: relative_path(path, self.runtime.data_root) for key, path in files.items()}

    def append_tool_output(self, run_id: str, stream: str, text: str) -> None:
        if not text:
            return
        stream = "stderr" if stream == "stderr" else "stdout"
        with self._lock:
            append_text(self._tool_path(run_id, stream), text)

    def script_log_files(self, run_id: str) -> dict[str, str]:
        files = {
            "script_stdout": self._script_path(run_id, "stdout"),
            "script_stderr": self._script_path(run_id, "stderr"),
        }
        for path in files.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        return {key: relative_path(path, self.runtime.data_root) for key, path in files.items()}

    def append_script_output(self, run_id: str, stream: str, text: str) -> None:
        if not text:
            return
        stream = "stderr" if stream == "stderr" else "stdout"
        with self._lock:
            append_text(self._script_path(run_id, stream), text)

    def maacore_log_offset(self) -> int:
        path = self._maacore_source_log()
        try:
            return path.stat().st_size
        except FileNotFoundError:
            return 0

    def capture_maacore_log(self, run_id: str, start_offset: int) -> str | None:
        source = self._maacore_source_log()
        try:
            size = source.stat().st_size
        except FileNotFoundError:
            return None
        offset = start_offset if 0 <= start_offset <= size else 0
        with source.open("rb") as handle:
            handle.seek(offset)
            content = handle.read()
        if not content:
            return None
        target = self.maacore_log_dir / f"{run_id}.log"
        target.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(target, content.decode("utf-8", errors="replace"))
        return relative_path(target, self.runtime.data_root)

    def enforce_retention(self) -> None:
        with self._lock:
            cutoff = datetime.now() - timedelta(days=max(0, self.retention.max_age_days))
            _prune_files(self.event_dir, max_count=self.retention.max_event_log_files, cutoff=cutoff)
            _prune_files(self.maa_cli_log_dir, max_count=self.retention.max_maa_cli_log_files, cutoff=cutoff)
            _prune_files(self.tool_log_dir, max_count=self.retention.max_tool_log_files, cutoff=cutoff)
            _prune_files(self.script_log_dir, max_count=self.retention.max_script_log_files, cutoff=cutoff)
            _prune_files(self.maacore_log_dir, max_count=self.retention.max_maacore_capture_files, cutoff=cutoff)
            _prune_dirs(self.runtime.generated_config_dir, max_count=self.retention.max_generated_config_dirs, cutoff=cutoff)
            _prune_files(self.runtime.run_log_dir, max_count=self.retention.max_legacy_run_log_files, cutoff=cutoff)
            _prune_maacore_debug(self.runtime.state_home / "maa" / "debug", self.retention, cutoff=cutoff)

    def _event_path(self, run_id: str) -> Path:
        return self.event_dir / f"{run_id}.jsonl"

    def _maa_cli_path(self, run_id: str, stream: str) -> Path:
        return self.maa_cli_log_dir / f"{run_id}.{stream}.log"

    def _tool_path(self, run_id: str, stream: str) -> Path:
        return self.tool_log_dir / f"{run_id}.{stream}.log"

    def _script_path(self, run_id: str, stream: str) -> Path:
        return self.script_log_dir / f"{run_id}.{stream}.log"

    def _maacore_source_log(self) -> Path:
        return self.runtime.state_home / "maa" / "debug" / "asst.log"


def configure_framework_logging(runtime: MaaRuntime, retention: LogRetentionPolicy | None = None) -> logging.Logger:
    policy = retention or LogRetentionPolicy()
    runtime.framework_log_dir.mkdir(parents=True, exist_ok=True)
    log_file = runtime.framework_log_dir / "framework.log"
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
    logger.debug("framework logging configured path=%s", relative_path(log_file, runtime.data_root))
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def _prune_files(directory: Path, *, max_count: int, cutoff: datetime) -> None:
    if not directory.exists():
        return
    files = [path for path in directory.rglob("*") if path.is_file()]
    expired = {path for path in files if _mtime(path) < cutoff}
    newest = sorted(files, key=_mtime, reverse=True)
    overflow = set(newest[max(0, max_count):]) if max_count > 0 else set(files)
    for path in sorted(expired | overflow, key=lambda item: str(item)):
        _unlink(path)


def _prune_dirs(directory: Path, *, max_count: int, cutoff: datetime) -> None:
    if not directory.exists():
        return
    dirs = [path for path in directory.iterdir() if path.is_dir()]
    expired = {path for path in dirs if _mtime(path) < cutoff}
    newest = sorted(dirs, key=_mtime, reverse=True)
    overflow = set(newest[max(0, max_count):]) if max_count > 0 else set(dirs)
    for path in sorted(expired | overflow, key=lambda item: str(item), reverse=True):
        _remove_tree(path)


def _prune_maacore_debug(directory: Path, policy: LogRetentionPolicy, *, cutoff: datetime) -> None:
    if not directory.exists():
        return
    asst_log = directory / "asst.log"
    if asst_log.exists() and asst_log.stat().st_size > policy.max_asst_log_bytes:
        rotated = directory / f"asst-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        asst_log.replace(rotated)
        asst_log.touch()
    files = [path for path in directory.rglob("*") if path.is_file() and path.name != "asst.log"]
    expired = {path for path in files if _mtime(path) < cutoff}
    newest = sorted(files, key=_mtime, reverse=True)
    overflow = set(newest[max(0, policy.max_maacore_debug_files):]) if policy.max_maacore_debug_files > 0 else set(files)
    for path in sorted(expired | overflow, key=lambda item: str(item)):
        _unlink(path)


def _remove_tree(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        _unlink(path)
        return
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            _remove_tree(child)
        else:
            _unlink(child)
    try:
        path.rmdir()
    except OSError:
        pass


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)


def _now() -> str:
    return server_now_iso()
