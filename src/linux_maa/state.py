from __future__ import annotations


def idle_response() -> dict[str, object]:
    """Return the standard idle-state dict for API responses."""
    return {"status": "idle", "output": []}


def state_or_idle(state: object | None) -> dict[str, object]:
    """Return state dict if not None, otherwise return idle_response()."""
    if state is None:
        return idle_response()
    return state.to_dict()  # type: ignore[attr-defined]
