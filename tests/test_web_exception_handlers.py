from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from fastapi import FastAPI, Request

from maa_auto_panel.config.manager import ConfigValidationFailure
from maa_auto_panel.errors import Conflict, CorruptState, InvalidRequest, ResourceNotFound, RuntimeUnavailable
from maa_auto_panel.web.exception_handlers import register_exception_handlers
from maa_auto_panel.web.routes.configs import create_config_router


def test_application_exception_handlers_return_stable_status_and_detail() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    cases = (
        (InvalidRequest("invalid input"), 400, "invalid input"),
        (ResourceNotFound("missing item"), 404, "missing item"),
        (Conflict("already active"), 409, "already active"),
        (RuntimeUnavailable("runtime missing"), 503, "runtime missing"),
    )
    for exc, status_code, detail in cases:
        response = asyncio.run(_handle(app, exc))
        assert response.status_code == status_code
        assert json.loads(response.body) == {"detail": detail}

    assert ValueError not in app.exception_handlers
    assert RuntimeError not in app.exception_handlers
    assert FileNotFoundError not in app.exception_handlers


def test_corrupt_state_handler_does_not_expose_storage_details() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    response = asyncio.run(_handle(app, CorruptState("invalid JSON at /private/state.json")))

    assert response.status_code == 500
    assert json.loads(response.body) == {"detail": "Stored application state is corrupt"}


def test_config_validation_handler_preserves_structured_422_response() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    result = SimpleNamespace(to_dict=lambda: {"valid": False, "errors": [{"message": "bad value"}]})

    response = asyncio.run(_handle(app, ConfigValidationFailure(result)))

    assert response.status_code == 422
    assert json.loads(response.body) == {
        "detail": {
            "message": "Configuration validation failed",
            "validation": {"valid": False, "errors": [{"message": "bad value"}]},
        }
    }


def test_config_route_lets_application_errors_reach_handlers() -> None:
    class Configs:
        def read(self, _kind: str, _name: str):
            raise ResourceNotFound("missing")

        def delete(self, _kind: str, _name: str):
            raise InvalidRequest("invalid kind")

    services = SimpleNamespace(
        runtime=SimpleNamespace(config_dir="config", data_root="data"),
        configs=Configs(),
    )
    router = create_config_router(services)
    read_config = next(route.endpoint for route in router.routes if route.path == "/api/configs/{kind}/{name}" and "GET" in route.methods)
    delete_config = next(route.endpoint for route in router.routes if route.path == "/api/configs/{kind}/{name}" and "DELETE" in route.methods)

    try:
        read_config("other", "missing")
    except ResourceNotFound as exc:
        assert str(exc) == "missing"
    else:
        raise AssertionError("read_config swallowed ResourceNotFound")

    try:
        delete_config("other", "name")
    except InvalidRequest as exc:
        assert str(exc) == "invalid kind"
    else:
        raise AssertionError("delete_config swallowed InvalidRequest")


async def _handle(app: FastAPI, exc: Exception):
    handler = app.exception_handlers[type(exc)]
    request = Request({"type": "http", "method": "GET", "path": "/test", "headers": []})
    return await handler(request, exc)
