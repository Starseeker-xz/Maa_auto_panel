from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from linux_maa.config import ConfigManager, FrameworkSettingsManager
from linux_maa.maa import MaaInfrastService, MaaRunManager, MaaRuntime, MaaStageService, MaintenanceActionManager, find_repo_root
from linux_maa.scheduler import ScheduleConfigManager, SchedulerService


@dataclass(frozen=True)
class WebServices:
    runtime: MaaRuntime
    configs: ConfigManager
    framework_settings: FrameworkSettingsManager
    runs: MaaRunManager
    maintenance: MaintenanceActionManager
    stages: MaaStageService
    infrast: MaaInfrastService
    schedule_configs: ScheduleConfigManager
    scheduler: SchedulerService


def create_services(repo_root: Path | None = None) -> WebServices:
    runtime = MaaRuntime(repo_root.resolve() if repo_root is not None else find_repo_root())
    configs = ConfigManager(runtime)
    framework_settings = FrameworkSettingsManager(runtime)
    schedule_configs = ScheduleConfigManager(runtime, configs)
    return WebServices(
        runtime=runtime,
        configs=configs,
        framework_settings=framework_settings,
        runs=MaaRunManager(runtime),
        maintenance=MaintenanceActionManager(runtime),
        stages=MaaStageService(runtime),
        infrast=MaaInfrastService(runtime),
        schedule_configs=schedule_configs,
        scheduler=SchedulerService(runtime, configs, framework_settings, schedule_configs),
    )
