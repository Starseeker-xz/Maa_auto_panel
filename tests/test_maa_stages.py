from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import maa_auto_panel.maa.stages as stage_module
from maa_auto_panel.config.tasks import FIGHT_STAGE_PLACEHOLDER, prepare_framework_task_config
from maa_auto_panel.maa.stages import CURRENT_STAGE_VALUE, MaaStageService, _load_stage_aliases, normalize_stage_plan_value


def fake_runtime(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        repo_root=tmp_path,
        cache_root=tmp_path / "cache",
        framework_maa_cache_dir=tmp_path / "cache" / "maa",
        cache_home=tmp_path / "cache",
        data_home=tmp_path / "data",
        data_root=tmp_path,
    )


def write_activity(runtime: SimpleNamespace, data: dict[str, object]) -> None:
    path = runtime.framework_maa_cache_dir / "StageActivityV2.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, object] | None = None,
        *,
        etag: str = "",
    ) -> None:
        self.status_code = status_code
        self.payload = payload
        self.headers = {"ETag": etag} if etag else {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, object] | None:
        return self.payload


def activity_stage(*, expires: str = "2026/08/03 03:59:59") -> dict[str, object]:
    return {
        "Official": {
            "sideStoryStage": {
                "AD": {
                    "MinimumRequired": "v6.14.0",
                    "Activity": {
                        "Tip": "SideStory「红丝绒」复刻",
                        "StageName": "红丝绒",
                        "UtcStartTime": "2026/07/20 04:00:00",
                        "UtcExpireTime": expires,
                        "TimeZone": 8,
                    },
                    "Stages": [{"Display": "AD-6", "Value": "AD-6"}],
                }
            }
        }
    }


def test_stage_candidates_refresh_into_framework_maa_cache(tmp_path: Path, monkeypatch) -> None:
    runtime = fake_runtime(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse(200, activity_stage(), etag='W/"activity-v1"')

    monkeypatch.setattr(stage_module.requests, "get", fake_get)
    monkeypatch.setattr(stage_module.time, "monotonic", lambda: 1.0)
    monkeypatch.setattr(stage_module, "_current_core_version", lambda runtime, errors: "6.14.2")

    response = MaaStageService(runtime).stage_candidates(
        now=datetime(2026, 7, 21, tzinfo=timezone.utc),
        include_unavailable=True,
    )

    cache_file = runtime.framework_maa_cache_dir / "StageActivityV2.json"
    assert cache_file.is_file()
    assert json.loads(cache_file.read_text(encoding="utf-8")) == activity_stage()
    assert cache_file.with_name("StageActivityV2.json.etag").read_text(encoding="utf-8").strip() == 'W/"activity-v1"'
    assert response["sources"]["activity_file"] == "cache/maa/StageActivityV2.json"  # type: ignore[index]
    assert any(stage["value"] == "AD-6" for stage in response["stages"])  # type: ignore[union-attr]
    assert calls == [
        {
            "url": stage_module.STAGE_ACTIVITY_URL,
            "headers": {},
            "timeout": stage_module.STAGE_ACTIVITY_REQUEST_TIMEOUT,
        }
    ]


def test_stage_candidates_revalidate_stale_cache_with_etag(tmp_path: Path, monkeypatch) -> None:
    runtime = fake_runtime(tmp_path)
    write_activity(runtime, activity_stage())
    cache_file = runtime.framework_maa_cache_dir / "StageActivityV2.json"
    etag_file = cache_file.with_name("StageActivityV2.json.etag")
    etag_file.write_text('W/"activity-v1"\n', encoding="utf-8")
    old_timestamp = 1_700_000_000
    os.utime(cache_file, (old_timestamp, old_timestamp))
    os.utime(etag_file, (old_timestamp, old_timestamp))
    calls: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse(304)

    monkeypatch.setattr(stage_module.requests, "get", fake_get)
    monkeypatch.setattr(stage_module, "_current_core_version", lambda runtime, errors: "6.14.2")

    response = MaaStageService(runtime).stage_candidates(now=datetime(2026, 7, 21, tzinfo=timezone.utc))

    assert response["errors"] == []
    assert etag_file.stat().st_mtime > old_timestamp
    assert calls[0]["headers"] == {"If-None-Match": 'W/"activity-v1"'}


def test_stage_candidates_ignore_orphan_etag_when_cache_is_missing(tmp_path: Path, monkeypatch) -> None:
    runtime = fake_runtime(tmp_path)
    etag_file = runtime.framework_maa_cache_dir / "StageActivityV2.json.etag"
    etag_file.parent.mkdir(parents=True)
    etag_file.write_text('W/"orphaned"\n', encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse(200, activity_stage(), etag='W/"activity-v2"')

    monkeypatch.setattr(stage_module.requests, "get", fake_get)
    monkeypatch.setattr(stage_module, "_current_core_version", lambda runtime, errors: "6.14.2")

    response = MaaStageService(runtime).stage_candidates(now=datetime(2026, 7, 21, tzinfo=timezone.utc))

    assert response["sources"]["activity_file"] == "cache/maa/StageActivityV2.json"  # type: ignore[index]
    assert calls[0]["headers"] == {}
    assert etag_file.read_text(encoding="utf-8").strip() == 'W/"activity-v2"'


def test_stage_candidates_keep_stale_cache_when_refresh_fails(tmp_path: Path, monkeypatch) -> None:
    runtime = fake_runtime(tmp_path)
    write_activity(runtime, activity_stage())
    cache_file = runtime.framework_maa_cache_dir / "StageActivityV2.json"
    old_timestamp = 1_700_000_000
    os.utime(cache_file, (old_timestamp, old_timestamp))
    monkeypatch.setattr(stage_module.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("offline")))
    monkeypatch.setattr(stage_module, "_current_core_version", lambda runtime, errors: "6.14.2")

    response = MaaStageService(runtime).stage_candidates(
        now=datetime(2026, 7, 21, tzinfo=timezone.utc),
        include_unavailable=True,
    )

    assert any(stage["value"] == "AD-6" for stage in response["stages"])  # type: ignore[union-attr]
    assert response["errors"] == ["更新 StageActivityV2 失败: offline"]


def test_stage_candidates_use_gui_display_aliases(tmp_path: Path, monkeypatch) -> None:
    runtime = fake_runtime(tmp_path)
    write_activity(runtime, {})
    monkeypatch.setattr(stage_module, "_current_core_version", lambda runtime, errors: "6.14.2")

    response = MaaStageService(runtime).stage_candidates(
        now=datetime(2026, 7, 21, tzinfo=timezone.utc),
        include_unavailable=True,
    )
    by_value = {stage["value"]: stage for stage in response["stages"]}

    assert by_value["CE-6"]["display"] == "龙门币-6/5"
    assert by_value["PR-D-2"]["display"] == "近/特芯片组"
    assert by_value["Annihilation"]["display"] == "当期剿灭"
    assert response["errors"] == []


def test_invalid_alias_file_falls_back_without_raising(tmp_path: Path) -> None:
    alias_file = tmp_path / "stage_aliases.json"
    alias_file.write_text('{"CE-6": 5, "": "empty", "AP-5": "红票-5"}', encoding="utf-8")
    errors: list[str] = []

    aliases = _load_stage_aliases(errors, alias_file)

    assert aliases == {"AP-5": "红票-5"}
    assert errors == ["关卡别名包含无效条目"]


def test_malformed_alias_file_falls_back_without_raising(tmp_path: Path) -> None:
    alias_file = tmp_path / "stage_aliases.json"
    alias_file.write_text("{", encoding="utf-8")
    errors: list[str] = []

    assert _load_stage_aliases(errors, alias_file) == {}
    assert errors[0].startswith("读取 关卡别名 失败:")


def test_resource_stage_keeps_weekday_availability(tmp_path: Path, monkeypatch) -> None:
    runtime = fake_runtime(tmp_path)
    write_activity(
        runtime,
        {
            "Official": {
                "resourceCollection": {
                    "UtcStartTime": "2026/01/01 00:00:00",
                    "UtcExpireTime": "2026/01/02 00:00:00",
                    "TimeZone": 8,
                    "IsResourceCollection": True,
                }
            }
        },
    )
    monkeypatch.setattr(stage_module, "_current_core_version", lambda runtime, errors: "6.14.2")
    service = MaaStageService(runtime)

    assert service.resolve_first_open_stage(["CE-6", "1-7"], now=datetime(2026, 7, 20, tzinfo=timezone.utc)) == "1-7"
    assert service.resolve_first_open_stage(["CE-6", "1-7"], now=datetime(2026, 7, 21, tzinfo=timezone.utc)) == "CE-6"


def test_custom_stage_is_eligible_but_known_closed_activity_is_skipped(tmp_path: Path, monkeypatch) -> None:
    runtime = fake_runtime(tmp_path)
    write_activity(runtime, activity_stage())
    monkeypatch.setattr(stage_module, "_current_core_version", lambda runtime, errors: "6.14.2")
    service = MaaStageService(runtime)
    after_activity = datetime(2026, 8, 4, tzinfo=timezone.utc)

    assert service.resolve_first_open_stage(["AD-6", "AD-3"], now=datetime(2026, 7, 21, tzinfo=timezone.utc)) == "AD-6"
    assert service.resolve_first_open_stage(["AD-6", " AD-3 ", "1-7"], now=after_activity) == "AD-3"
    assert service.resolve_first_open_stage(["H10-1-HARD", "1-7"], now=after_activity) == "H10-1-HARD"


def test_current_last_and_blank_values_keep_empty_maa_semantics(tmp_path: Path, monkeypatch) -> None:
    runtime = fake_runtime(tmp_path)
    write_activity(runtime, {})
    monkeypatch.setattr(stage_module, "_current_core_version", lambda runtime, errors: "6.14.2")

    assert normalize_stage_plan_value("   ") == CURRENT_STAGE_VALUE
    assert MaaStageService(runtime).resolve_first_open_stage([CURRENT_STAGE_VALUE]) == ""


def test_framework_preprocess_passes_custom_stage_to_maacore(tmp_path: Path, monkeypatch) -> None:
    runtime = fake_runtime(tmp_path)
    write_activity(runtime, activity_stage())
    monkeypatch.setattr(stage_module, "_current_core_version", lambda runtime, errors: "6.14.2")
    data: dict[str, object] = {
        "tasks": [
            {
                "name": "自定义关卡",
                "type": "Fight",
                "params": {"stage": FIGHT_STAGE_PLACEHOLDER},
                "framework": {
                    "managed_params": {
                        "stage": {
                            "type": "runtime",
                            "handler": "fight_stage",
                            "items": [
                                {"value": "  AD-3  ", "enabled": True},
                                {"value": "1-7", "enabled": True},
                            ],
                        }
                    }
                },
            }
        ]
    }

    prepared = prepare_framework_task_config(data, runtime)

    assert prepared["tasks"][0]["params"]["stage"] == "AD-3"  # type: ignore[index]
