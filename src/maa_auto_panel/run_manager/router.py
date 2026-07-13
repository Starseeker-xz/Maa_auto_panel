from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from fastapi import APIRouter, Request

from maa_auto_panel.errors import ResourceNotFound
from maa_auto_panel.run_manager.state import LiveRun
from maa_auto_panel.web.sse import state_event_stream


class RunControlManager(Protocol):
    def current_response(self, *, include_logs: bool = True) -> dict[str, object]: ...

    def wait_for_change(self, last_version: int, timeout: float | None = None) -> int: ...

    def get(self, run_id: str) -> LiveRun | None: ...

    def stop_current(self) -> LiveRun: ...

    def force_stop_current(self) -> LiveRun: ...

    def stop(self, run_id: str) -> LiveRun: ...

    def force_stop(self, run_id: str) -> LiveRun: ...


@dataclass(frozen=True)
class RunControlRoutes:
    """Options for registering common live-run status, SSE, and stop routes."""

    manager: RunControlManager
    stop_target: Literal["current", "run_id", "both"] = "current"
    include_get_by_id: bool = False
    expose_stop: bool = True
    expose_force_stop: bool = True
    current_not_found_detail: str = "No run active"
    run_not_found_detail: str = "Run not found"


def register_run_control_routes(router: APIRouter, options: RunControlRoutes) -> None:
    manager = options.manager

    @router.get("/current")
    def current_run() -> dict[str, object]:
        return manager.current_response()

    @router.get("/current/events")
    def current_run_events(request: Request):
        return state_event_stream(request, manager.current_response, manager.wait_for_change)

    if options.expose_stop and options.stop_target in {"current", "both"}:

        @router.post("/current/stop")
        def stop_current_run() -> dict[str, object]:
            try:
                return manager.stop_current().to_dict()
            except ResourceNotFound as exc:
                raise ResourceNotFound(options.current_not_found_detail) from exc

    if options.expose_force_stop and options.stop_target in {"current", "both"}:

        @router.post("/current/force-stop")
        def force_stop_current_run() -> dict[str, object]:
            try:
                return manager.force_stop_current().to_dict()
            except ResourceNotFound as exc:
                raise ResourceNotFound(options.current_not_found_detail) from exc

    if options.include_get_by_id:

        @router.get("/{run_id}")
        def get_run(run_id: str) -> dict[str, object]:
            state = manager.get(run_id)
            if state is None:
                raise ResourceNotFound(options.run_not_found_detail)
            return state.to_dict()

    if options.expose_stop and options.stop_target in {"run_id", "both"}:

        @router.post("/{run_id}/stop")
        def stop_run(run_id: str) -> dict[str, object]:
            try:
                return manager.stop(run_id).to_dict()
            except ResourceNotFound as exc:
                raise ResourceNotFound(options.run_not_found_detail) from exc

    if options.expose_force_stop and options.stop_target in {"run_id", "both"}:

        @router.post("/{run_id}/force-stop")
        def force_stop_run(run_id: str) -> dict[str, object]:
            try:
                return manager.force_stop(run_id).to_dict()
            except ResourceNotFound as exc:
                raise ResourceNotFound(options.run_not_found_detail) from exc
