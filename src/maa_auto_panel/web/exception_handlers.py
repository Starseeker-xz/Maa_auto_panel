from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from maa_auto_panel.config.manager import ConfigValidationFailure
from maa_auto_panel.diagnostics import get_logger
from maa_auto_panel.errors import Conflict, CorruptState, InvalidRequest, ResourceNotFound, RuntimeUnavailable


logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register the small application exception model at the HTTP boundary."""

    async def invalid_request_handler(_request: Request, exc: InvalidRequest) -> JSONResponse:
        return _detail_response(400, exc)

    async def resource_not_found_handler(_request: Request, exc: ResourceNotFound) -> JSONResponse:
        return _detail_response(404, exc)

    async def conflict_handler(_request: Request, exc: Conflict) -> JSONResponse:
        return _detail_response(409, exc)

    async def corrupt_state_handler(request: Request, exc: CorruptState) -> JSONResponse:
        logger.error(
            "corrupt application state method=%s path=%s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(status_code=500, content={"detail": "Stored application state is corrupt"})

    async def runtime_unavailable_handler(_request: Request, exc: RuntimeUnavailable) -> JSONResponse:
        return _detail_response(503, exc)

    async def config_validation_handler(_request: Request, exc: ConfigValidationFailure) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "message": "Configuration validation failed",
                    "validation": exc.result.to_dict(),
                }
            },
        )

    app.add_exception_handler(InvalidRequest, invalid_request_handler)
    app.add_exception_handler(ResourceNotFound, resource_not_found_handler)
    app.add_exception_handler(Conflict, conflict_handler)
    app.add_exception_handler(CorruptState, corrupt_state_handler)
    app.add_exception_handler(RuntimeUnavailable, runtime_unavailable_handler)
    app.add_exception_handler(ConfigValidationFailure, config_validation_handler)


def _detail_response(status_code: int, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})
