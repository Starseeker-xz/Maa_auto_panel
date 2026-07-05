from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from linux_maa.scheduler.models import ScheduleEntry


CLIENT_GAME_DAY_OFFSETS: dict[str, int] = {
    "Official": 4,
    "Bilibili": 4,
    "txwy": 4,
    "Txwy": 4,
    "YoStarJP": 5,
    "YoStarKR": 5,
}


@dataclass(frozen=True)
class GameDayInfo:
    client: str
    game_day: str
    timezone_name: str
    reset_local_time: str
    order: list[str]
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "client": self.client,
            "game_day": self.game_day,
            "timezone_name": self.timezone_name,
            "reset_local_time": self.reset_local_time,
            "order": self.order,
            "message": self.message,
        }


def effective_timezone(name: str) -> tzinfo:
    raw = (name or "UTC").strip()
    if not raw:
        return timezone.utc
    upper = raw.upper()
    if upper in {"UTC", "Z"}:
        return timezone.utc
    try:
        return ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        pass

    parsed = upper
    if parsed.startswith("UTC"):
        parsed = parsed[3:]
    if parsed.startswith("GMT"):
        parsed = parsed[3:]
    if not parsed:
        return timezone.utc
    sign = -1 if parsed.startswith("-") else 1
    value = parsed[1:] if parsed.startswith(("+", "-")) else parsed
    if ":" in value:
        hours_text, minutes_text = value.split(":", 1)
        minutes = sign * (int(hours_text) * 60 + int(minutes_text))
    else:
        minutes = sign * int(value) * 60
    return timezone(timedelta(minutes=minutes))


def game_day_timezone(client: str) -> timezone:
    return timezone(timedelta(hours=CLIENT_GAME_DAY_OFFSETS.get(client, CLIENT_GAME_DAY_OFFSETS["Official"])))


def game_day_key(moment: datetime, *, client: str) -> str:
    return moment.astimezone(game_day_timezone(client)).date().isoformat()


def reset_local_time(client: str, local_tz: tzinfo, *, now: datetime | None = None) -> time:
    current = now or datetime.now(local_tz)
    game_tz = game_day_timezone(client)
    game_midnight = current.astimezone(game_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return game_midnight.astimezone(local_tz).time().replace(second=0, microsecond=0)


def sort_entries_for_game_day(entries: list[ScheduleEntry], *, client: str, local_tz: tzinfo, now: datetime | None = None) -> list[ScheduleEntry]:
    reset = _minutes(reset_local_time(client, local_tz, now=now))
    return sorted(entries, key=lambda entry: ((_minutes(parse_time(entry.time)) - reset) % 1440, entry.name))


def game_day_info(entries: list[ScheduleEntry], *, client: str, timezone_name: str, now: datetime | None = None) -> GameDayInfo:
    local_tz = effective_timezone(timezone_name)
    current = now or datetime.now(local_tz)
    sorted_entries = sort_entries_for_game_day(entries, client=client, local_tz=local_tz, now=current)
    reset_time = reset_local_time(client, local_tz, now=current).strftime("%H:%M")
    order = [entry.id for entry in sorted_entries]
    return GameDayInfo(
        client=client,
        game_day=game_day_key(current, client=client),
        timezone_name=timezone_name,
        reset_local_time=reset_time,
        order=order,
        message=f"服务器: {client} · 游戏日更新时间: 本地 {reset_time}\n游戏日运行顺序: "
        + " -> ".join(entry.time for entry in sorted_entries),
    )


def extract_client_type(task_config: dict[str, object]) -> str:
    tasks = task_config.get("tasks")
    if isinstance(tasks, list):
        for task in tasks:
            if not isinstance(task, dict) or task.get("type") != "StartUp":
                continue
            params = task.get("params")
            if isinstance(params, dict) and isinstance(params.get("client_type"), str) and params["client_type"]:
                return str(params["client_type"])
    root_client = task_config.get("client_type")
    return str(root_client) if isinstance(root_client, str) and root_client else "Official"


def parse_time(value: str) -> time:
    hour_text, minute_text = value.split(":", 1)
    return time(hour=int(hour_text), minute=int(minute_text))


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute
