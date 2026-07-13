import asyncio

from maa_auto_panel.lifecycle import clear_shutdown_request, request_shutdown
from maa_auto_panel.web.sse import _state_events, build_cursor_patch, build_state_patch


def test_state_patch_replaces_mutated_current_retry() -> None:
    previous = {
        "run": {"id": "run-1", "status": "running", "updated_at": "2026-07-01T15:00:00"},
        "retries": [
            {
                "id": "run-1-1",
                "run_id": "run-1",
                "retry_index": 1,
                "retry_group": 1,
                "status": "running",
                "updated_at": "2026-07-01T15:00:00",
                "closed": False,
                "log_entries": [{"id": "log-1", "kind": "task", "status": "running"}],
            }
        ],
    }
    current = {
        "run": {"id": "run-1", "status": "running", "updated_at": "2026-07-01T15:10:00"},
        "retries": [
            {
                "id": "run-1-1",
                "run_id": "run-1",
                "retry_index": 1,
                "retry_group": 1,
                "status": "succeeded",
                "updated_at": "2026-07-01T15:10:00",
                "closed": True,
                "log_entries": [{"id": "log-1", "kind": "task", "status": "succeeded"}],
                "summary_messages": [{"text": "重试结果：✔️ 启动", "tone": "success"}],
            }
        ],
    }

    patch = build_state_patch(previous, current, 42)

    assert patch is not None
    assert patch["stream_version"] == 42
    assert patch["state"] == {"run": current["run"]}
    assert patch["retries"] == {"replace_from": 0, "items": current["retries"]}


def test_cursor_patch_resends_open_retry_when_client_count_matches() -> None:
    current = {
        "run": {"id": "run-1", "status": "running"},
        "retries": [
            {"id": "run-1-1", "retry_index": 1, "closed": True, "log_entries": []},
            {"id": "run-1-2", "retry_index": 2, "closed": False, "log_entries": [{"id": "log-2"}]},
        ],
    }

    patch = build_cursor_patch(current, {"retries": 2}, 7)

    assert patch["state"] == {"run": current["run"]}
    assert patch["retries"] == {"replace_from": 1, "items": [current["retries"][1]]}


def test_cursor_patch_sends_only_new_closed_retries() -> None:
    current = {
        "run": {"id": "run-1", "status": "running"},
        "retries": [
            {"id": "run-1-1", "retry_index": 1, "closed": True, "log_entries": []},
            {"id": "run-1-2", "retry_index": 2, "closed": True, "log_entries": []},
        ],
    }

    patch = build_cursor_patch(current, {"retries": 1}, 8)

    assert patch["retries"] == {"replace_from": 1, "items": [current["retries"][1]]}


def test_state_stream_stops_after_server_disconnect_without_waiting_for_keepalive() -> None:
    class FakeRequest:
        query_params = {}
        headers = {}

        def __init__(self) -> None:
            self.checks = 0

        async def is_disconnected(self) -> bool:
            self.checks += 1
            return self.checks >= 2

    async def exercise() -> None:
        request = FakeRequest()
        stream = _state_events(
            request,  # type: ignore[arg-type]
            lambda: {"run": {"status": "idle"}, "retries": [], "stream_version": 0},
            lambda version, timeout: version if version >= 0 else 0,
        )
        first = await anext(stream)
        assert "data:" in first
        try:
            await anext(stream)
        except StopAsyncIteration:
            pass
        else:
            raise AssertionError("SSE stream did not stop after disconnect")

    asyncio.run(exercise())


def test_state_stream_stops_when_process_shutdown_is_requested() -> None:
    class ConnectedRequest:
        query_params = {}
        headers = {}

        async def is_disconnected(self) -> bool:
            return False

    async def exercise() -> None:
        stream = _state_events(
            ConnectedRequest(),  # type: ignore[arg-type]
            lambda: {"run": {"status": "idle"}, "retries": [], "stream_version": 0},
            lambda version, timeout: version if version >= 0 else 0,
        )
        await anext(stream)
        request_shutdown()
        try:
            await anext(stream)
        except StopAsyncIteration:
            pass
        else:
            raise AssertionError("SSE stream did not stop for process shutdown")

    clear_shutdown_request()
    try:
        asyncio.run(exercise())
    finally:
        clear_shutdown_request()
