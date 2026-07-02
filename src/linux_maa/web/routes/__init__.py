from linux_maa.web.routes.configs import create_config_router
from linux_maa.web.routes.history import create_history_router
from linux_maa.web.routes.maintenance import create_maintenance_router
from linux_maa.web.routes.maa import create_maa_router
from linux_maa.web.routes.runs import create_run_router
from linux_maa.web.routes.schedules import create_schedule_router
from linux_maa.web.routes.settings import create_settings_router

__all__ = [
    "create_config_router",
    "create_history_router",
    "create_maintenance_router",
    "create_maa_router",
    "create_run_router",
    "create_schedule_router",
    "create_settings_router",
]
