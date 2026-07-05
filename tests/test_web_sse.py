from linux_maa.web.sse import build_cursor_patch, build_state_patch


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
