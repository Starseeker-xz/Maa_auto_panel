from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MaaRuntime:
    """Immutable path layout for MAA installation: config, data, cache, state, logs, generated configs."""
    repo_root: Path

    @property
    def maa_bin(self) -> Path:
        return self.repo_root / "runtime" / "maa" / "bin" / "maa"

    @property
    def config_dir(self) -> Path:
        return self.repo_root / "config" / "maa"

    @property
    def framework_config_dir(self) -> Path:
        return self.repo_root / "config" / "linux-maa"

    @property
    def debug_dir(self) -> Path:
        return self.repo_root / "debug"

    @property
    def framework_log_dir(self) -> Path:
        return self.debug_dir / "linux-maa"

    @property
    def framework_event_log_dir(self) -> Path:
        return self.framework_log_dir / "events"

    @property
    def framework_external_log_dir(self) -> Path:
        return self.framework_log_dir / "external"

    @property
    def maa_cli_log_dir(self) -> Path:
        return self.framework_external_log_dir / "maa-cli"

    @property
    def maacore_capture_log_dir(self) -> Path:
        return self.framework_external_log_dir / "maacore"

    @property
    def schedule_config_dir(self) -> Path:
        return self.framework_config_dir / "schedules"

    @property
    def script_dir(self) -> Path:
        return self.framework_config_dir / "scripts"

    @property
    def data_home(self) -> Path:
        return self.repo_root / "runtime" / "maa" / "data"

    @property
    def cache_home(self) -> Path:
        return self.repo_root / "runtime" / "maa" / "cache"

    @property
    def state_home(self) -> Path:
        return self.repo_root / "runtime" / "maa" / "state"

    @property
    def run_log_dir(self) -> Path:
        return self.repo_root / "runtime" / "maa" / "run-logs"

    @property
    def generated_config_dir(self) -> Path:
        return self.repo_root / "runtime" / "maa" / "generated-configs"

    @property
    def framework_state_dir(self) -> Path:
        return self.repo_root / "state" / "linux-maa"

    @property
    def run_state_dir(self) -> Path:
        return self.framework_state_dir / "run-history"

    @property
    def scheduler_state_dir(self) -> Path:
        return self.framework_state_dir / "scheduler"

    @property
    def framework_history_dir(self) -> Path:
        return self.repo_root / "history" / "linux-maa"

    @property
    def run_history_dir(self) -> Path:
        return self.framework_history_dir / "runs"

    def env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.maa_bin.parent}:{env.get('PATH', '')}"
        env["MAA_CONFIG_DIR"] = str(self.config_dir)
        env["XDG_DATA_HOME"] = str(self.data_home)
        env["XDG_CACHE_HOME"] = str(self.cache_home)
        env["XDG_STATE_HOME"] = str(self.state_home)
        env["MAA_LOG_PREFIX"] = "Always"
        return env


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upward from path to locate repository root containing pyproject.toml and src/linux_maa."""
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        if (path / "pyproject.toml").exists() and (path / "src" / "linux_maa").exists():
            return path
    return current
