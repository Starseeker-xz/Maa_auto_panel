from __future__ import annotations

from fastapi import HTTPException

from linux_maa.config import ConfigValidationFailure
from linux_maa.state import state_or_idle


def validation_exception(message: str, exc: ConfigValidationFailure) -> HTTPException:
    """Build HTTP 422 exception with structured ConfigValidationFailure detail body."""
    return HTTPException(
        status_code=422,
        detail={
            "message": message,
            "validation": exc.result.to_dict(),
        },
    )
