from linux_maa.web.sse import build_cursor_patch, build_state_patch


def test_state_patch_replaces_mutated_log_tail() -> None:
    previous = {
        "id": "run-1",
        "status": "running",
        "output": ["started\n"],
        "task_results": [
            {
                "type": "task",
                "name": "StartUp",
                "status": "running",
                "messages": [],
                "lines": ["StartUp Start"],
            }
        ],
        "log_entries": [
            {
                "type": "block",
                "id": "log-1",
                "source": "maa-cli:stderr",
                "kind": "task",
                "name": "StartUp",
                "status": "running",
                "messages": [],
                "lines": ["StartUp Start"],
            }
        ],
    }
    current = {
        **previous,
        "updated_at": "2026-07-01T15:10:00",
        "output": ["started\n", "finished\n"],
        "task_results": [
            {
                "type": "task",
                "name": "StartUp",
                "status": "succeeded",
                "messages": [{"type": "text", "text": "done", "tone": "info"}],
                "lines": ["StartUp Start", "StartUp Completed"],
            }
        ],
        "log_entries": [
            {
                "type": "block",
                "id": "log-1",
                "source": "maa-cli:stderr",
                "kind": "task",
                "name": "StartUp",
                "status": "succeeded",
                "messages": [{"text": "done", "tone": "info"}],
                "lines": ["StartUp Start", "StartUp Completed"],
            }
        ],
    }

    patch = build_state_patch(previous, current, 42)

    assert patch is not None
    assert patch["stream_version"] == 42
    assert patch["state"] == {"id": "run-1", "status": "running", "updated_at": "2026-07-01T15:10:00"}
    assert patch["output"] == {"replace_from": 1, "items": ["finished\n"]}
    assert patch["task_results"] == {"replace_from": 0, "items": current["task_results"]}
    assert patch["log_entries"] == {"replace_from": 0, "items": current["log_entries"]}


def test_cursor_patch_uses_client_offsets_and_resends_mutable_tail() -> None:
    current = {
        "id": "run-1",
        "status": "running",
        "output": ["line 1\n", "line 2\n", "line 3\n"],
        "task_results": [
            {"type": "task", "name": "StartUp", "status": "succeeded", "messages": [], "lines": []},
            {"type": "task", "name": "Fight", "status": "running", "messages": [], "lines": []},
        ],
        "log_entries": [
            {"type": "block", "id": "log-1", "source": "maa-cli:stderr", "kind": "task", "name": "StartUp", "status": "succeeded", "messages": [], "lines": []},
            {"type": "block", "id": "log-2", "source": "maa-cli:stderr", "kind": "task", "name": "Fight", "status": "running", "messages": [], "lines": []},
        ],
    }

    patch = build_cursor_patch(
        current,
        {"output": 2, "task_results": 1, "log_entries": 1},
        7,
    )

    assert patch["state"] == {"id": "run-1", "status": "running"}
    assert patch["output"] == {"replace_from": 2, "items": ["line 3\n"]}
    assert patch["task_results"] == {"replace_from": 0, "items": current["task_results"]}
    assert patch["log_entries"] == {"replace_from": 0, "items": current["log_entries"]}


def test_cursor_patch_resends_full_log_entries_even_when_client_length_matches() -> None:
    current = {
        "id": "run-1",
        "status": "running",
        "output": ["line 1\n"],
        "task_results": [],
        "log_entries": [
            {"type": "block", "id": "log-1", "source": "maa-cli:stdout", "kind": "summary", "title": "运行摘要", "status": "succeeded", "messages": [], "lines": ["Summary"]},
            {"type": "block", "id": "log-2", "source": "maa-cli:stdout", "kind": "line", "messages": [{"text": "done", "tone": "info"}], "lines": ["done"]},
        ],
    }

    patch = build_cursor_patch(
        current,
        {"output": 1, "task_results": 0, "log_entries": 2},
        8,
    )

    assert "output" not in patch
    assert "task_results" not in patch
    assert patch["log_entries"] == {"replace_from": 0, "items": current["log_entries"]}
