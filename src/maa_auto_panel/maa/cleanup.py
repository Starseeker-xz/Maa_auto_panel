from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from maa_auto_panel.diagnostics import get_logger
from maa_auto_panel.paths import MaaInstallation


logger = get_logger(__name__)


@dataclass(frozen=True)
class MaaDebugRetentionPolicy:
    max_age_days: int = 14
    max_debug_files: int = 500
    max_asst_log_bytes: int = 50 * 1024 * 1024


def enforce_maa_debug_retention(
    installation: MaaInstallation,
    policy: MaaDebugRetentionPolicy | None = None,
) -> None:
    """Best-effort retention for files owned by the MAA installation."""
    retention = policy or MaaDebugRetentionPolicy()
    try:
        _enforce_debug_retention(installation.state_home / "maa" / "debug", retention)
    except OSError:
        logger.exception("MAA debug retention failed path=%s", installation.state_home / "maa" / "debug")


def _enforce_debug_retention(directory: Path, policy: MaaDebugRetentionPolicy) -> None:
    if not directory.exists():
        return

    asst_log = directory / "asst.log"
    if asst_log.is_file() and asst_log.stat().st_size > policy.max_asst_log_bytes:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        asst_log.replace(directory / f"asst-{timestamp}.log")
        asst_log.touch()

    files = [path for path in directory.rglob("*") if path.is_file() and path != asst_log]
    cutoff = datetime.now() - timedelta(days=max(0, policy.max_age_days))
    expired = {path for path in files if datetime.fromtimestamp(path.stat().st_mtime) < cutoff}
    newest = sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)
    overflow = set(newest[max(0, policy.max_debug_files) :]) if policy.max_debug_files > 0 else set(files)
    for path in sorted(expired | overflow, key=str):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
