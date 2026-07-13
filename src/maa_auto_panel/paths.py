from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DATA_DIR_ENV = "MAA_AUTO_PANEL_DATA_DIR"
RUNTIME_DIR_ENV = "MAA_AUTO_PANEL_RUNTIME_DIR"
CACHE_DIR_ENV = "MAA_AUTO_PANEL_CACHE_DIR"


def _configured_root(value: Path | None, env_name: str, default: Path) -> Path:
    if value is not None:
        return value.expanduser().resolve()
    configured = os.environ.get(env_name, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return default.resolve()


@dataclass(frozen=True)
class ApplicationPaths:
    """Read-only assets installed with the application."""

    root: Path

    @property
    def frontend_dist(self) -> Path:
        return self.root / "frontend" / "dist"

    @property
    def maa_schema_dir(self) -> Path:
        return self.root / "docs" / "maa-cli" / "schemas"


@dataclass(frozen=True)
class FrameworkPaths:
    """Framework-owned persistent configuration, state, history, and diagnostics."""

    root: Path

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def history_dir(self) -> Path:
        return self.root / "history"

    @property
    def debug_dir(self) -> Path:
        return self.root / "debug"

    @property
    def framework_config_dir(self) -> Path:
        return self.config_dir / "framework"

    @property
    def framework_state_dir(self) -> Path:
        return self.state_dir / "framework"

    @property
    def run_state_dir(self) -> Path:
        return self.framework_state_dir / "run-history"

    @property
    def scheduler_state_dir(self) -> Path:
        return self.framework_state_dir / "scheduler"

    @property
    def framework_history_dir(self) -> Path:
        return self.history_dir / "framework"

    @property
    def run_history_dir(self) -> Path:
        return self.framework_history_dir / "runs"

    @property
    def framework_log_dir(self) -> Path:
        return self.debug_dir / "framework"

    @property
    def framework_event_log_dir(self) -> Path:
        return self.framework_log_dir / "events"

    @property
    def framework_external_log_dir(self) -> Path:
        return self.framework_log_dir / "external"


@dataclass(frozen=True)
class CachePaths:
    """Disposable application caches that are safe to rebuild."""

    root: Path

    @property
    def downloads_dir(self) -> Path:
        return self.root / "downloads"


@dataclass(frozen=True)
class MaaInstallation:
    """MAA integration paths, separate from generic framework storage."""

    root: Path
    config_dir: Path

    @property
    def binary(self) -> Path:
        return self.root / "bin" / "maa"

    @property
    def data_home(self) -> Path:
        return self.root / "data"

    @property
    def cache_home(self) -> Path:
        return self.root / "cache"

    @property
    def state_home(self) -> Path:
        return self.root / "state"

    @property
    def generated_config_dir(self) -> Path:
        return self.root / "generated-configs"

    @property
    def run_log_dir(self) -> Path:
        return self.root / "run-logs"


@dataclass(frozen=True)
class PathLayout:
    application: ApplicationPaths
    framework: FrameworkPaths
    cache: CachePaths
    maa: MaaInstallation

    @classmethod
    def create(
        cls,
        app_root: Path,
        *,
        data_root: Path | None = None,
        runtime_root: Path | None = None,
        cache_root: Path | None = None,
    ) -> PathLayout:
        application = ApplicationPaths(app_root.expanduser().resolve())
        framework = FrameworkPaths(
            _configured_root(data_root, DATA_DIR_ENV, application.root / "data")
        )
        cache = CachePaths(
            _configured_root(cache_root, CACHE_DIR_ENV, application.root / "cache")
        )
        maa = MaaInstallation(
            root=_configured_root(runtime_root, RUNTIME_DIR_ENV, application.root / "runtime") / "maa",
            config_dir=framework.config_dir / "maa",
        )
        return cls(application=application, framework=framework, cache=cache, maa=maa)
