from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import StreamingResponse

from maa_auto_panel.lifecycle import shutdown_requested


StateProvider = Callable[[], dict[str, object]]
StateChangeWaiter = Callable[[int, float | None], int]

LIST_FIELDS = ("retries",)
CURSOR_QUERY_PARAMS = {"retries": "retries_from"}
DISCONNECT_POLL_SECONDS = 1.0
KEEP_ALIVE_SECONDS = 15.0


def state_event_stream(request: Request, provider: StateProvider, wait_for_change: StateChangeWaiter) -> StreamingResponse:
    """Create StreamingResponse delivering SSE for live state updates (reset, patch, keep-alive)."""
    return StreamingResponse(
        _state_events(request, provider, wait_for_change),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _state_events(request: Request, provider: StateProvider, wait_for_change: StateChangeWaiter):
    try:
        requested_version = _requested_version(request)
        cursors = _requested_cursors(request)
        wait_version = await asyncio.to_thread(wait_for_change, -1, 0)
        previous, version = await asyncio.to_thread(_snapshot, provider, wait_version)

        if requested_version is None:
            yield _format_sse_data(build_state_reset(previous, version), event_id=version)
        elif requested_version < version:
            yield _format_sse_data(build_cursor_patch(previous, cursors, version), event_id=version)
        elif requested_version > version:
            yield _format_sse_data(build_state_reset(previous, version), event_id=version)

        next_keep_alive = time.monotonic() + KEEP_ALIVE_SECONDS
        while True:
            if shutdown_requested() or await request.is_disconnected():
                break

            wait_version = await asyncio.to_thread(wait_for_change, version, DISCONNECT_POLL_SECONDS)
            if wait_version == version:
                if shutdown_requested() or await request.is_disconnected():
                    break
                if time.monotonic() >= next_keep_alive:
                    yield ": keep-alive\n\n"
                    next_keep_alive = time.monotonic() + KEEP_ALIVE_SECONDS
                continue

            current, next_version = await asyncio.to_thread(_snapshot, provider, wait_version)
            patch = build_state_patch(previous, current, next_version)
            previous = current
            version = next_version
            if patch is not None:
                yield _format_sse_data(patch, event_id=version)
    except asyncio.CancelledError:
        raise


def build_state_reset(current: dict[str, object], version: int) -> dict[str, object]:
    """Build full-state reset SSE payload from current state dict and stream version."""
    return {
        "type": "reset",
        **current,
        "stream_version": version,
    }


def build_cursor_patch(current: dict[str, object], cursors: dict[str, int], version: int) -> dict[str, object]:
    """Build cursor-based incremental patch SSE payload, resending the mutable current retry when needed."""
    payload: dict[str, object] = {
        "type": "patch",
        "stream_version": version,
        "state": _state_fields(current),
    }
    for field in LIST_FIELDS:
        current_items = _list_field(current, field)
        replace_from = cursors.get(field, 0)
        if replace_from > len(current_items):
            replace_from = 0
        elif replace_from == len(current_items) and current_items and not _item_closed(current_items[-1]):
            replace_from -= 1
        if replace_from < len(current_items):
            payload[field] = {
                "replace_from": replace_from,
                "items": current_items[replace_from:],
            }
    return payload


def build_state_patch(previous: dict[str, object], current: dict[str, object], version: int) -> dict[str, object] | None:
    """Diff previous and current state dicts to produce minimal patch SSE payload, or None if unchanged."""
    payload: dict[str, object] = {
        "type": "patch",
        "stream_version": version,
    }
    previous_state = _state_fields(previous)
    current_state = _state_fields(current)
    if current_state != previous_state:
        payload["state"] = current_state

    for field in LIST_FIELDS:
        patch = _list_patch(_list_field(previous, field), _list_field(current, field))
        if patch is not None:
            payload[field] = patch

    return payload if len(payload) > 2 else None


def _snapshot(provider: StateProvider, default_version: int) -> tuple[dict[str, object], int]:
    payload = dict(provider())
    version = _parse_int(payload.pop("stream_version", None))
    return payload, version if version is not None else default_version


def _state_fields(payload: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if key not in LIST_FIELDS and key != "stream_version"}


def _list_field(payload: dict[str, object], field: str) -> list[object]:
    value = payload.get(field)
    return list(value) if isinstance(value, list) else []


def _list_patch(previous: list[object], current: list[object]) -> dict[str, object] | None:
    replace_from = 0
    limit = min(len(previous), len(current))
    while replace_from < limit and previous[replace_from] == current[replace_from]:
        replace_from += 1
    if replace_from == len(previous) and replace_from == len(current):
        return None
    return {
        "replace_from": replace_from,
        "items": current[replace_from:],
    }


def _item_closed(value: object) -> bool:
    return isinstance(value, dict) and value.get("closed") is True


def _requested_version(request: Request) -> int | None:
    versions = [
        parsed
        for parsed in (
            _parse_int(request.query_params.get("after")),
            _parse_int(request.headers.get("last-event-id")),
        )
        if parsed is not None
    ]
    return max(versions) if versions else None


def _requested_cursors(request: Request) -> dict[str, int]:
    cursors: dict[str, int] = {}
    for field, query_param in CURSOR_QUERY_PARAMS.items():
        value = _parse_int(request.query_params.get(query_param))
        cursors[field] = max(0, value or 0)
    return cursors


def _parse_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _format_sse_data(payload: dict[str, object], *, event_id: int | None = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"data: {json.dumps(payload, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"
