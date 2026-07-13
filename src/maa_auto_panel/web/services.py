from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading
import time

from maa_auto_panel.config.app_settings import FrameworkSettingsManager
from maa_auto_panel.config.manager import ConfigManager
from maa_auto_panel.diagnostics import Diagnostics, get_logger
from maa_auto_panel.maa.cleanup import enforce_maa_debug_retention
from maa_auto_panel.maa.infrast import MaaInfrastService
from maa_auto_panel.maa.maintenance import MaintenanceActionManager
from maa_auto_panel.maa.runner import MaaRunManager
from maa_auto_panel.maa.runtime import MaaRuntime, find_repo_root
from maa_auto_panel.maa.stages import MaaStageService
from maa_auto_panel.notifications import NotificationService, NotificationSettingsManager
from maa_auto_panel.run_manager.coordinator import RunCoordinator
from maa_auto_panel.run_manager.manager import GenericRunManager
from maa_auto_panel.run_manager.store import RunStateStore
from maa_auto_panel.scheduler.config import ScheduleConfigManager
from maa_auto_panel.scheduler.service import SchedulerService
from maa_auto_panel.scheduler.state import SchedulerStateStore
from maa_auto_panel.tools.manager import ToolRunManager

logger = get_logger(__name__)


NORMAL_SHUTDOWN_SECONDS = 60.0
FORCE_SHUTDOWN_SECONDS = 15.0


@dataclass
class WebServices:
    """Immutable aggregate holding all long-lived service instances needed by the web layer."""
    runtime: MaaRuntime
    run_state: RunStateStore
    scheduler_state: SchedulerStateStore
    diagnostics: Diagnostics
    run_coordinator: RunCoordinator
    configs: ConfigManager
    framework_settings: FrameworkSettingsManager
    notification_settings: NotificationSettingsManager
    notifications: NotificationService
    runs: MaaRunManager
    maintenance: MaintenanceActionManager
    tools: ToolRunManager
    stages: MaaStageService
    infrast: MaaInfrastService
    schedule_configs: ScheduleConfigManager
    scheduler: SchedulerService
    _close_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def start(self) -> None:
        self.notifications.inspect_runtime_presence()
        self.scheduler.start()

    def close(
        self,
        *,
        normal_timeout: float = NORMAL_SHUTDOWN_SECONDS,
        force_timeout: float = FORCE_SHUTDOWN_SECONDS,
    ) -> None:
        with self._close_lock:
            if self._closed:
                return
            started = time.monotonic()
            managers = self._run_managers()

            self.scheduler.begin_shutdown()
            for manager in managers:
                manager.begin_shutdown()
            self.run_coordinator.begin_shutdown()

            normal_deadline = time.monotonic() + max(0.0, normal_timeout)
            self.scheduler.join_until(normal_deadline)
            for manager in managers:
                manager.request_shutdown_stop()
            remaining = _join_managers_until(managers, normal_deadline)

            if remaining:
                logger.warning("forcing active runs during shutdown count=%s", len(remaining))
                for manager in remaining:
                    manager.request_shutdown_force()
                force_deadline = time.monotonic() + max(0.0, force_timeout)
                remaining = _join_managers_until(remaining, force_deadline)

            elapsed = time.monotonic() - started
            if remaining:
                logger.error("shutdown finished with live run threads count=%s elapsed=%.2fs", len(remaining), elapsed)
            else:
                logger.info("application shutdown completed elapsed=%.2fs", elapsed)
            self.diagnostics.close_logging()
            self._closed = True

    def _run_managers(self) -> tuple[GenericRunManager, ...]:
        return (self.runs.runs, self.scheduler.runs, self.maintenance.runs, self.tools.runs)

    def discard_terminal_run(self, run_id: str) -> None:
        for manager in self._run_managers():
            manager.discard_terminal(run_id)


def _join_managers_until(
    managers: tuple[GenericRunManager, ...],
    deadline: float,
) -> list[GenericRunManager]:
    remaining: list[GenericRunManager] = []
    for manager in managers:
        if not manager.join_until(deadline):
            remaining.append(manager)
    return remaining


def create_services(
    repo_root: Path | None = None,
    *,
    data_root: Path | None = None,
    cache_root: Path | None = None,
) -> WebServices:
    """Instantiate and wire together all backend services; return populated WebServices container."""
    runtime = MaaRuntime(
        repo_root.resolve() if repo_root is not None else find_repo_root(),
        data_root=data_root,
        cache_root=cache_root,
    )
    framework_paths = runtime.layout.framework
    path_references = runtime.path_references
    diagnostics = Diagnostics(framework_paths, path_references)
    diagnostics.configure_logging()
    enforce_maa_debug_retention(runtime.layout.maa)
    run_state = RunStateStore(framework_paths, path_references)
    recovered_runs = run_state.recover_interrupted_runs()
    run_state.enforce_retention()
    diagnostics.enforce_retention(protected_paths=run_state.owned_paths())
    scheduler_state = SchedulerStateStore(runtime)
    scheduler_state.enforce_retention()
    if recovered_runs:
        logger.warning("recovered interrupted run records count=%s", recovered_runs)
    configs = ConfigManager(runtime)
    framework_settings = FrameworkSettingsManager(runtime)
    notification_settings = NotificationSettingsManager(runtime)
    notifications = NotificationService(runtime, notification_settings)
    schedule_configs = ScheduleConfigManager(runtime, configs)
    run_coordinator = RunCoordinator()
    return WebServices(
        runtime=runtime,
        run_state=run_state,
        scheduler_state=scheduler_state,
        diagnostics=diagnostics,
        run_coordinator=run_coordinator,
        configs=configs,
        framework_settings=framework_settings,
        notification_settings=notification_settings,
        notifications=notifications,
        runs=MaaRunManager(runtime, run_state, diagnostics, framework_settings, configs, run_coordinator, notifications),
        maintenance=MaintenanceActionManager(runtime, run_state, diagnostics, framework_settings, run_coordinator),
        tools=ToolRunManager(runtime, configs, run_state, diagnostics, framework_settings, run_coordinator),
        stages=MaaStageService(runtime),
        infrast=MaaInfrastService(runtime),
        schedule_configs=schedule_configs,
        scheduler=SchedulerService(
            runtime,
            configs,
            framework_settings,
            schedule_configs,
            run_state,
            scheduler_state,
            diagnostics,
            run_coordinator,
            notifications,
        ),
    )
