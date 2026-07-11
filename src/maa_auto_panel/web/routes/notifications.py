from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from maa_auto_panel.lifecycle import shutdown_requested
from maa_auto_panel.web.services import WebServices


def create_notifications_router(services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api/notifications", tags=["notifications"])

    @router.get("/settings")
    def read_settings() -> dict[str, object]:
        return services.notification_settings.response()

    @router.put("/settings")
    def save_settings(payload: dict[str, object]) -> dict[str, object]:
        return services.notification_settings.write(payload)

    @router.get("/events")
    def events(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _event_stream(request, services),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router


async def _event_stream(request: Request, services: WebServices):
    sequence = _sequence(request.headers.get("last-event-id") or request.query_params.get("after"))
    replay_through = services.notifications.latest_sequence()
    keep_alive = time.monotonic() + 15
    while True:
        if shutdown_requested() or await request.is_disconnected():
            return
        events = await asyncio.to_thread(services.notifications.events_after, sequence)
        for event in events:
            sequence = int(event["sequence"])
            payload = json.dumps(
                {**event, "delivery": {"replayed": sequence <= replay_through}},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            yield f"id: {sequence}\ndata: {payload}\n\n"
        if events:
            keep_alive = time.monotonic() + 15
            continue
        await asyncio.to_thread(services.notifications.wait_for_change, sequence, 1.0)
        if time.monotonic() >= keep_alive:
            yield ": keep-alive\n\n"
            keep_alive = time.monotonic() + 15


def _sequence(value: object) -> int:
    try:
        return max(0, int(str(value or 0)))
    except ValueError:
        return 0
