from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MaaRuntime:
    repo_root: Path

    @property
    def maa_bin(self) -> Path:
        return self.repo_root / "runtime" / "maa" / "bin" / "maa"

    @property
    def config_dir(self) -> Path:
        return self.repo_root / "config" / "maa"

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

    def env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.maa_bin.parent}:{env.get('PATH', '')}"
        env["MAA_CONFIG_DIR"] = str(self.config_dir)
        env["XDG_DATA_HOME"] = str(self.data_home)
        env["XDG_CACHE_HOME"] = str(self.cache_home)
        env["XDG_STATE_HOME"] = str(self.state_home)
        return env


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        if (path / "pyproject.toml").exists() and (path / "src" / "linux_maa").exists():
            return path
    return current
