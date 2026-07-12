from __future__ import annotations

from pathlib import Path

import pytest

from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.paths import CACHE_DIR_ENV, DATA_DIR_ENV, RUNTIME_DIR_ENV
from maa_auto_panel.storage.path_references import PathReferenceResolver
from maa_auto_panel.storage.trash import TrashManager
from maa_auto_panel.tools.game.update import PackageManager


def test_runtime_separates_application_framework_data_integration_runtime_and_cache(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)

    assert runtime.repo_root == tmp_path
    assert runtime.data_root == tmp_path / "data"
    assert runtime.runtime_root == tmp_path / "runtime"
    assert runtime.cache_root == tmp_path / "cache"
    assert runtime.config_dir == tmp_path / "data/config/maa"
    assert runtime.run_history_dir == tmp_path / "data/history/framework/runs"
    assert runtime.maa_bin == tmp_path / "runtime/maa/bin/maa"
    assert runtime.download_dir == tmp_path / "cache/downloads"
    assert runtime.frontend_dist == tmp_path / "frontend/dist"
    assert runtime.maa_schema_dir == tmp_path / "docs/maa-cli/schemas"


def test_runtime_path_overrides_prefer_explicit_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "env-data"))
    monkeypatch.setenv(RUNTIME_DIR_ENV, str(tmp_path / "env-runtime"))
    monkeypatch.setenv(CACHE_DIR_ENV, str(tmp_path / "env-cache"))

    from_environment = MaaRuntime(tmp_path / "app")
    explicit = MaaRuntime(
        tmp_path / "app",
        data_root=tmp_path / "explicit-data",
        runtime_root=tmp_path / "explicit-runtime",
        cache_root=tmp_path / "explicit-cache",
    )

    assert from_environment.data_root == tmp_path / "env-data"
    assert from_environment.runtime_root == tmp_path / "env-runtime"
    assert from_environment.cache_root == tmp_path / "env-cache"
    assert explicit.data_root == tmp_path / "explicit-data"
    assert explicit.runtime_root == tmp_path / "explicit-runtime"
    assert explicit.cache_root == tmp_path / "explicit-cache"


def test_package_manifest_stores_logical_download_references(tmp_path: Path) -> None:
    manager = PackageManager(tmp_path / "cache/downloads")
    apk = manager.download_dir / "game.apk"
    apk.write_bytes(b"apk")

    manager.update_package_status(1, "verified", path=apk)

    assert manager.get_package_info(1)["path"] == "downloads:game.apk"  # type: ignore[index]
    assert manager.get_verified_package_path(1) == apk

    with pytest.raises(ValueError, match="escapes download directory"):
        manager.update_package_status(2, "verified", path=tmp_path / "outside.apk")


def test_logical_path_references_survive_relocated_roots_and_reject_escape(tmp_path: Path) -> None:
    source = PathReferenceResolver({"runtime": tmp_path / "host-a/runtime"})
    reference = source.reference("runtime", tmp_path / "host-a/runtime/maa/generated-configs/run-1")

    relocated = PathReferenceResolver({"runtime": tmp_path / "host-b/runtime"})

    assert reference == "runtime:maa/generated-configs/run-1"
    assert relocated.resolve(reference) == tmp_path / "host-b/runtime/maa/generated-configs/run-1"
    with pytest.raises(ValueError, match="escapes root"):
        relocated.resolve("runtime:../secret")
    with pytest.raises(ValueError, match="Expected logical root"):
        relocated.resolve("runtime:maa", expected_root="framework")


def test_trash_record_uses_framework_logical_references(tmp_path: Path) -> None:
    data_root = tmp_path / "external-data"
    source = data_root / "config/maa/tasks/example.toml"
    source.parent.mkdir(parents=True)
    source.write_text("[task]\n", encoding="utf-8")

    record = TrashManager(
        data_root / "config/maa/.trash", logical_root=data_root
    ).move(source, label="task:example.toml")

    assert record.original_path == "framework:config/maa/tasks/example.toml"
    assert record.trash_path.startswith("framework:config/maa/.trash/")
