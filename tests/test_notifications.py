from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.notifications import NotificationService, NotificationSettingsManager
from maa_auto_panel.run_manager.state import LiveRetry, LiveRun
from maa_auto_panel.web.routes.notifications import _event_stream


class _ConnectedRequest:
    headers: dict[str, str] = {}
    query_params: dict[str, str] = {}

    async def is_disconnected(self) -> bool:
        return False


def test_notification_settings_expose_five_stable_tags_and_round_trip(tmp_path: Path) -> None:
    settings = NotificationSettingsManager(MaaRuntime(tmp_path))
    response = settings.response()

    assert [item["id"] for item in response["tags"]] == [
        "runtime.maa.missing",
        "runtime.maa.update_available",
        "run.maa.manual.finished",
        "run.maa.schedule.auto.finished",
        "run.maa.schedule.manual.finished",
    ]

    tags = list(response["tags"])
    tags[0] = {**tags[0], "toast": False, "external": True}
    saved = settings.write({"tags": tags})

    assert saved["tags"][0]["toast"] is False
    assert saved["tags"][0]["external"] is True
    assert settings.path.is_file()


def test_runtime_conditions_are_deduplicated_and_respect_toast_setting(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    service = NotificationService(runtime)

    service.inspect_runtime_presence()
    service.inspect_runtime_presence()
    events = service.events_after(0)

    assert len(events) == 1
    assert events[0]["tag"] == "runtime.maa.missing"
    assert events[0]["data"] == {"missing_components": ["maa-cli", "MaaCore"]}
    assert events[0]["important"] is True
    assert events[0]["replay_toast"] is True


def test_toast_disabled_notification_still_enters_recent_stack(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    settings = NotificationSettingsManager(runtime)
    response = settings.response()
    tags = [{**item, "toast": False} if item["id"] == "run.maa.manual.finished" else item for item in response["tags"]]
    settings.write({"tags": tags})
    service = NotificationService(runtime, settings)

    event = service.publish("run.maa.manual.finished", "success", "完成", "运行成功")

    assert event.toast is False
    assert service.latest_sequence() == 1
    assert service.events_after(0)[0]["title"] == "完成"


def test_notification_stream_marks_backlog_replayed_and_new_event_live(tmp_path: Path) -> None:
    service = NotificationService(MaaRuntime(tmp_path))
    service.publish("run.maa.manual.finished", "success", "旧通知", "离线期间产生")

    async def scenario() -> tuple[dict[str, object], dict[str, object]]:
        backlog_stream = _event_stream(_ConnectedRequest(), SimpleNamespace(notifications=service))
        backlog = _sse_payload(await anext(backlog_stream))
        await backlog_stream.aclose()

        live_stream = _event_stream(_ConnectedRequest(), SimpleNamespace(notifications=service))
        first = await anext(live_stream)
        assert _sse_payload(first)["delivery"] == {"replayed": True}
        live_task = asyncio.create_task(anext(live_stream))
        await asyncio.sleep(0.02)
        service.publish("run.maa.manual.finished", "success", "新通知", "在线期间产生")
        live = _sse_payload(await asyncio.wait_for(live_task, timeout=2))
        await live_stream.aclose()
        return backlog, live

    backlog, live = asyncio.run(scenario())
    assert backlog["delivery"] == {"replayed": True}
    assert live["delivery"] == {"replayed": False}


def _sse_payload(chunk: str) -> dict[str, object]:
    data_line = next(line for line in chunk.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line.removeprefix("data: "))
    assert isinstance(payload, dict)
    return payload


def test_maa_run_notifications_distinguish_manual_and_schedule_trigger_and_ignore_stop(tmp_path: Path) -> None:
    service = NotificationService(MaaRuntime(tmp_path))
    retry = LiveRetry("run-1-1", "run-1", 1, 1, "start", "end", status="succeeded", closed=True)

    manual = LiveRun("run-1", "manual", "daily", "succeeded", "start", "end", retries=[retry])
    automatic = LiveRun("run-2", "schedule", "早班", "failed", "start", "end", metadata={"trigger": "schedule"}, retries=[retry])
    triggered = LiveRun("run-3", "schedule", "晚班", "succeeded", "start", "end", metadata={"trigger": "manual"}, retries=[retry])
    stopped = LiveRun("run-4", "manual", "stop", "stopped", "start", "end", retries=[retry])

    for run in (manual, automatic, triggered, stopped):
        service.notify_run_finished(run)

    events = service.events_after(0)
    assert [event["tag"] for event in events] == [
        "run.maa.manual.finished",
        "run.maa.schedule.auto.finished",
        "run.maa.schedule.manual.finished",
    ]
    assert [event["severity"] for event in events] == ["success", "error", "success"]
    assert [event["replay_toast"] for event in events] == [False, True, False]


def test_update_notification_only_covers_cli_and_core(tmp_path: Path) -> None:
    service = NotificationService(MaaRuntime(tmp_path))
    info = {
        "latest": {
            "maa_cli": {"update_available": True},
            "maa_core": {"update_available": False},
            "hot_resource": {"update_available": True},
        }
    }

    service.observe_update_info(info)
    service.observe_update_info(info)

    events = service.events_after(0)
    assert len(events) == 1
    assert events[0]["data"] == {"components": ["maa-cli"]}
