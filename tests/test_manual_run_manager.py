from pathlib import Path

from maa_auto_panel.config.app_settings import FrameworkSettingsManager
from maa_auto_panel.config.manager import ConfigManager
from maa_auto_panel.diagnostics import Diagnostics
from maa_auto_panel.maa.runner import MaaRunManager, MaaRunRequest
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.coordinator import RunCoordinator
from maa_auto_panel.run_manager.store import RunStateStore


def test_manual_run_manager_skips_disabled_task_and_persists_retry(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    tasks_dir = runtime.config_dir / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "daily.toml").write_text(
        """
[[tasks]]
type = "StartUp"
name = "Startup"

[tasks.params]
enable = false
""".lstrip(),
        encoding="utf-8",
    )
    store = RunStateStore(runtime.layout.framework, runtime.path_references)
    manager = MaaRunManager(
        runtime,
        store,
        Diagnostics(runtime.layout.framework, runtime.path_references),
        FrameworkSettingsManager(runtime),
        ConfigManager(runtime),
        RunCoordinator(),
    )

    state = manager.start(MaaRunRequest(task="daily", retry_count=3))
    assert state.thread is not None
    state.thread.join(timeout=5)
    assert not state.thread.is_alive()

    payload = manager.current_response()
    assert payload["run"]["status"] == "skipped"  # type: ignore[index]
    assert payload["run"]["max_retries"] == 3  # type: ignore[index]
    assert len(payload["retries"]) == 1  # type: ignore[arg-type]
    assert payload["retries"][0]["status"] == "skipped"  # type: ignore[index]
    assert payload["retries"][0]["closed"] is True  # type: ignore[index]

    stored = store.run(state.id)
    assert stored.status == "skipped"
    retries = store.retries(state.id)
    assert len(retries) == 1
    assert retries[0]["status"] == "skipped"
