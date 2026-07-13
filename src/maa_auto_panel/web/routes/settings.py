from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from maa_auto_panel.config.app_settings import FrameworkSettingsManager
from maa_auto_panel.config.manager import ConfigManager, ConfigValidationFailure
from maa_auto_panel.maa.maintenance import MaintenanceActionManager
from maa_auto_panel.notifications import NotificationSettingsManager
from maa_auto_panel.state import state_or_idle
from maa_auto_panel.web.responses import validation_exception
from maa_auto_panel.web.services import WebServices


class SaveSettingsPayload(BaseModel):
    framework: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    maa_cli: dict[str, Any] = Field(default_factory=dict)
    notifications: dict[str, Any] = Field(default_factory=dict)


def create_settings_router(services: WebServices) -> APIRouter:
    """Create APIRouter with endpoints for the settings API group."""
    router = APIRouter(prefix="/api/settings", tags=["settings"])
    configs = services.configs
    framework_settings = services.framework_settings
    maintenance = services.maintenance
    notification_settings = services.notification_settings

    @router.get("")
    def read_settings() -> dict[str, object]:
        return settings_response(configs, framework_settings, maintenance, notification_settings)

    @router.put("")
    def save_settings(payload: SaveSettingsPayload) -> dict[str, object]:
        try:
            profile_validation = configs.schema_validator.validate_profile_config(payload.profile)
            if not profile_validation.valid:
                raise ConfigValidationFailure(profile_validation)
            cli_validation = configs.schema_validator.validate_cli_config(payload.maa_cli)
            if not cli_validation.valid:
                raise ConfigValidationFailure(cli_validation)
            framework_settings.write(payload.framework)
            configs.write_profile_config("default", payload.profile)
            configs.write_cli_config(payload.maa_cli)
            notification_settings.write(payload.notifications)
            return settings_response(configs, framework_settings, maintenance, notification_settings)
        except ConfigValidationFailure as exc:
            raise validation_exception("Settings validation failed", exc) from exc

    return router


def settings_response(
    configs: ConfigManager,
    framework_settings: FrameworkSettingsManager,
    maintenance: MaintenanceActionManager,
    notification_settings: NotificationSettingsManager,
) -> dict[str, object]:
    return {
        "framework": framework_settings.read(),
        "profile": configs.read_profile_config("default"),
        "maa_cli": configs.read_cli_config(),
        "maintenance": state_or_idle(maintenance.current()),
        "notifications": notification_settings.response(),
    }
