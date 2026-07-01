from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import StreamingResponse

from linux_maa.web.responses import state_or_idle


StateProvider = Callable[[], object | None]
StateChangeWaiter = Callable[[int, float | None], int]


def state_event_stream(request: Request, provider: StateProvider, wait_for_change: StateChangeWaiter) -> StreamingResponse:
    return StreamingResponse(
        _state_events(request, provider, wait_for_change),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _state_events(request: Request, provider: StateProvider, wait_for_change: StateChangeWaiter):
    version = await asyncio.to_thread(wait_for_change, -1, 0)
    yield _format_sse_data(state_or_idle(provider()))

    while True:
        if await request.is_disconnected():
            break

        next_version = await asyncio.to_thread(wait_for_change, version, 15)
        if next_version == version:
            yield ": keep-alive\n\n"
            continue

        version = next_version
        yield _format_sse_data(state_or_idle(provider()))


def _format_sse_data(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
