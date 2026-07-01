from __future__ import annotations


def idle_response() -> dict[str, object]:
    return {"status": "idle", "output": []}


def state_or_idle(state: object | None) -> dict[str, object]:
    if state is None:
        return idle_response()
    return state.to_dict()  # type: ignore[attr-defined]
