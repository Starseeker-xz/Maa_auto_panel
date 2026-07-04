from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from linux_maa.config import ConfigManager, FrameworkSettingsManager
from linux_maa.diagnostics import Diagnostics, get_logger
from linux_maa.maa import MaaInfrastService, MaaRunManager, MaaRuntime, MaaStageService, MaintenanceActionManager, find_repo_root
from linux_maa.run_state import RunStateStore
from linux_maa.scheduler import ScheduleConfigManager, SchedulerService
from linux_maa.tools import ToolRunManager

logger = get_logger(__name__)


@dataclass(frozen=True)
class WebServices:
    """Immutable aggregate holding all long-lived service instances needed by the web layer."""
    runtime: MaaRuntime
    run_state: RunStateStore
    diagnostics: Diagnostics
    configs: ConfigManager
    framework_settings: FrameworkSettingsManager
    runs: MaaRunManager
    maintenance: MaintenanceActionManager
    tools: ToolRunManager
    stages: MaaStageService
    infrast: MaaInfrastService
    schedule_configs: ScheduleConfigManager
    scheduler: SchedulerService


def create_services(repo_root: Path | None = None) -> WebServices:
    """Instantiate and wire together all backend services; return populated WebServices container."""
    runtime = MaaRuntime(repo_root.resolve() if repo_root is not None else find_repo_root())
    diagnostics = Diagnostics(runtime)
    diagnostics.configure_logging()
    diagnostics.enforce_retention()
    run_state = RunStateStore(runtime)
    run_state.enforce_retention()
    recovered_runs = run_state.recover_interrupted_runs()
    if recovered_runs:
        logger.warning("recovered interrupted run records count=%s", recovered_runs)
    configs = ConfigManager(runtime)
    framework_settings = FrameworkSettingsManager(runtime)
    schedule_configs = ScheduleConfigManager(runtime, configs)
    return WebServices(
        runtime=runtime,
        run_state=run_state,
        diagnostics=diagnostics,
        configs=configs,
        framework_settings=framework_settings,
        runs=MaaRunManager(runtime, run_state, diagnostics),
        maintenance=MaintenanceActionManager(runtime, run_state, diagnostics),
        tools=ToolRunManager(runtime, configs, run_state, diagnostics),
        stages=MaaStageService(runtime),
        infrast=MaaInfrastService(runtime),
        schedule_configs=schedule_configs,
        scheduler=SchedulerService(runtime, configs, framework_settings, schedule_configs, run_state, diagnostics),
    )
