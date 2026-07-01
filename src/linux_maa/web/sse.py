from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import StreamingResponse

from linux_maa.web.responses import state_or_idle


StateProvider = Callable[[], object | None]


def state_event_stream(request: Request, provider: StateProvider) -> StreamingResponse:
    return StreamingResponse(
        _state_events(request, provider),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _state_events(request: Request, provider: StateProvider):
    last_signature: tuple[object, ...] | None = None
    last_heartbeat = time.monotonic()

    while True:
        if await request.is_disconnected():
            break

        payload = state_or_idle(provider())
        signature = _state_signature(payload)
        if signature != last_signature:
            last_signature = signature
            last_heartbeat = time.monotonic()
            yield _format_sse_data(payload)
        elif time.monotonic() - last_heartbeat >= 15:
            last_heartbeat = time.monotonic()
            yield ": keep-alive\n\n"

        await asyncio.sleep(0.5)


def _state_signature(payload: dict[str, object]) -> tuple[object, ...]:
    return (
        payload.get("id"),
        payload.get("status"),
        payload.get("updated_at"),
        payload.get("return_code"),
        payload.get("log_file"),
        len(payload.get("log_entries") or []),
        len(payload.get("output") or []),
    )


def _format_sse_data(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
