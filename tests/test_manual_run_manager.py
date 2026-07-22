import json
from pathlib import Path
import subprocess
import sys

from maa_auto_panel.config.app_settings import FrameworkSettingsManager
from maa_auto_panel.config.manager import ConfigManager
from maa_auto_panel.diagnostics import Diagnostics
from maa_auto_panel.maa.runner import MaaRunManager, MaaRunRequest
from maa_auto_panel.maa.results import MaaTaskDescriptor
from maa_auto_panel.maa.retry import MaaRetrySession
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.coordinator import RunCoordinator
from maa_auto_panel.run_manager.store import RunStateStore


class FakeRetryContext:
    def __init__(self, retry_index: int) -> None:
        self.retry_index = retry_index
        self.retry_id = f"run-{retry_index}"
        self.events: list[str] = []

    def add_event(self, text: str, *, tone: str = "info") -> None:
        self.events.append(f"{tone}:{text}")

    def configure_log(self, callback) -> None:
        return None


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
    store = RunStateStore(runtime.layout.data, runtime.path_references)
    manager = MaaRunManager(
        runtime,
        store,
        Diagnostics(runtime.layout.data, runtime.path_references),
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


def test_maa_retry_session_rereads_source_and_materializes_retry_task_plan(tmp_path: Path) -> None:
    runtime = MaaRuntime(tmp_path)
    diagnostics = Diagnostics(runtime.layout.data, runtime.path_references)
    tasks_dir = runtime.config_dir / "tasks"
    tasks_dir.mkdir(parents=True)
    source = tasks_dir / "daily.toml"

    def write_source(stage: str) -> None:
        source.write_text(
            f"""
[[tasks]]
type = "StartUp"
name = "Startup"

[tasks.framework]
id = "startup"

[tasks.params]
enable = false
stage = "{stage}"

[[tasks]]
type = "Award"
name = "Award"

[tasks.framework]
id = "award"

[tasks.params]
enable = true
""".lstrip(),
            encoding="utf-8",
        )

    write_source("first")
    session = MaaRetrySession(
        runtime,
        diagnostics,
        task="daily",
        profile_name="default",
        log_level=1,
        generated_run_id="shared-run",
    )
    descriptor = MaaTaskDescriptor(task_id="startup", source_name="StartUp", name="Startup")

    first = session.prepare_retry(FakeRetryContext(1), [descriptor])  # type: ignore[arg-type]
    write_source("second")
    second = session.prepare_retry(FakeRetryContext(2), [descriptor])  # type: ignore[arg-type]

    generated_tasks = runtime.generated_config_dir / "shared-run" / "tasks"
    first_data = json.loads((generated_tasks / f"{first.cmd[2]}.json").read_text(encoding="utf-8"))
    second_data = json.loads((generated_tasks / f"{second.cmd[2]}.json").read_text(encoding="utf-8"))
    assert first.cmd[2].endswith("retry-1")
    assert second.cmd[2].endswith("retry-2")
    assert [task["type"] for task in second_data["tasks"]] == ["StartUp"]
    assert first_data["tasks"][0]["params"]["stage"] == "first"
    assert second_data["tasks"][0]["params"] == {"enable": True, "stage": "second"}
    assert first.cwd == runtime.maa_working_dir
    assert second.cwd == runtime.maa_working_dir

    subprocess.run(
        [sys.executable, "-c", "from pathlib import Path; Path('debug/map').mkdir(parents=True); Path('debug/map/OF-1.jpeg').write_bytes(b'map')"],
        cwd=first.cwd,
        check=True,
    )
    assert (runtime.maa_working_dir / "debug/map/OF-1.jpeg").read_bytes() == b"map"
    assert not (runtime.repo_root / "debug/map/OF-1.jpeg").exists()
