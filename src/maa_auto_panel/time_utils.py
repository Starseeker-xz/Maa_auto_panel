from __future__ import annotations

from datetime import datetime


def server_now() -> datetime:
    """Current server-local time with an explicit UTC offset."""
    return datetime.now().astimezone()


def server_now_iso() -> str:
    return server_now().isoformat(timespec="seconds")


def server_time_text() -> str:
    return server_now().strftime("%H:%M:%S")


def server_datetime_from_text(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).astimezone().isoformat(timespec="seconds")
        except ValueError:
            continue
    return None
