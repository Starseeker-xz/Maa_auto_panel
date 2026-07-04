from __future__ import annotations

from fastapi import HTTPException

from linux_maa.config.manager import ConfigValidationFailure


def validation_exception(message: str, exc: ConfigValidationFailure) -> HTTPException:
    """Build HTTP 422 exception with structured ConfigValidationFailure detail body."""
    return HTTPException(
        status_code=422,
        detail={
            "message": message,
            "validation": exc.result.to_dict(),
        },
    )
