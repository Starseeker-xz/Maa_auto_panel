from __future__ import annotations

import os
from pathlib import Path

from maa_auto_panel.paths import PathLayout
from maa_auto_panel.storage.path_references import PathReferenceResolver


class MaaRuntime:
    """Aggregate runtime view over separated application, framework, cache, and MAA paths."""

    def __init__(
        self,
        repo_root: Path,
        *,
        data_root: Path | None = None,
        runtime_root: Path | None = None,
        cache_root: Path | None = None,
    ) -> None:
        self.layout = PathLayout.create(
            repo_root,
            data_root=data_root,
            runtime_root=runtime_root,
            cache_root=cache_root,
        )
        self.path_references = PathReferenceResolver(
            {
                "framework": self.layout.framework.root,
                "runtime": self.layout.maa.root.parent,
                "cache": self.layout.cache.root,
            }
        )

    @property
    def repo_root(self) -> Path:
        return self.layout.application.root

    @property
    def data_root(self) -> Path:
        return self.layout.framework.root

    @property
    def cache_root(self) -> Path:
        return self.layout.cache.root

    @property
    def runtime_root(self) -> Path:
        return self.layout.maa.root.parent

    @property
    def download_dir(self) -> Path:
        return self.layout.cache.downloads_dir

    @property
    def frontend_dist(self) -> Path:
        return self.layout.application.frontend_dist

    @property
    def maa_schema_dir(self) -> Path:
        return self.layout.application.maa_schema_dir

    @property
    def maa_bin(self) -> Path:
        return self.layout.maa.binary

    @property
    def config_dir(self) -> Path:
        return self.layout.maa.config_dir

    @property
    def framework_config_dir(self) -> Path:
        return self.layout.framework.config_dir / "framework"

    @property
    def debug_dir(self) -> Path:
        return self.layout.framework.debug_dir

    @property
    def framework_log_dir(self) -> Path:
        return self.debug_dir / "framework"

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
        return self.layout.maa.data_home

    @property
    def cache_home(self) -> Path:
        return self.layout.maa.cache_home

    @property
    def state_home(self) -> Path:
        return self.layout.maa.state_home

    @property
    def run_log_dir(self) -> Path:
        return self.layout.maa.run_log_dir

    @property
    def generated_config_dir(self) -> Path:
        return self.layout.maa.generated_config_dir

    @property
    def framework_state_dir(self) -> Path:
        return self.layout.framework.state_dir / "framework"

    @property
    def run_state_dir(self) -> Path:
        return self.framework_state_dir / "run-history"

    @property
    def scheduler_state_dir(self) -> Path:
        return self.framework_state_dir / "scheduler"

    @property
    def framework_history_dir(self) -> Path:
        return self.layout.framework.history_dir / "framework"

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
    """Walk upward from path to locate repository root containing pyproject.toml and src/maa_auto_panel."""
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        if (path / "pyproject.toml").exists() and (path / "src" / "maa_auto_panel").exists():
            return path
    return current
