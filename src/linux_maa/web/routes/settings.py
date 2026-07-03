from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from linux_maa.config import ConfigManager, ConfigValidationFailure, FrameworkSettingsManager
from linux_maa.maa import MaintenanceActionManager
from linux_maa.web.responses import state_or_idle, validation_exception
from linux_maa.web.services import WebServices


class SaveSettingsPayload(BaseModel):
    framework: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    maa_cli: dict[str, Any] = Field(default_factory=dict)


def create_settings_router(services: WebServices) -> APIRouter:
    """Create APIRouter with endpoints for the settings API group."""
    router = APIRouter(prefix="/api/settings", tags=["settings"])
    configs = services.configs
    framework_settings = services.framework_settings
    maintenance = services.maintenance

    @router.get("")
    def read_settings() -> dict[str, object]:
        try:
            return settings_response(configs, framework_settings, maintenance)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Settings source not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
            return settings_response(configs, framework_settings, maintenance)
        except ConfigValidationFailure as exc:
            raise validation_exception("Settings validation failed", exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router


def settings_response(
    configs: ConfigManager,
    framework_settings: FrameworkSettingsManager,
    maintenance: MaintenanceActionManager,
) -> dict[str, object]:
    return {
        "framework": framework_settings.read(),
        "profile": configs.read_profile_config("default"),
        "maa_cli": configs.read_cli_config(),
        "maintenance": state_or_idle(maintenance.current()),
    }
