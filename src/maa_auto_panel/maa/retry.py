from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import tomllib

from maa_auto_panel.config.tasks import TASK_SUFFIXES, prepare_framework_task_config
from maa_auto_panel.diagnostics import Diagnostics
from maa_auto_panel.errors import CorruptState
from maa_auto_panel.maa.cleanup import enforce_maa_debug_retention
from maa_auto_panel.maa.log_templates import begin_maa_task_sequence
from maa_auto_panel.maa.results import MaaTaskDescriptor, MaaTaskResultCollector
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.context import RetryContext
from maa_auto_panel.utils import resolve_existing_named_file, slugify, write_text_atomic


@dataclass(frozen=True)
class MaaRetryOutcome:
    """MAA-specific facts produced by one retry; policies decide what happens next."""

    task_results: list[dict[str, object]]
    status_by_task_id: dict[str, str]
    generated_config_dir: str
    diagnostic_log_file: str | None


class MaaRetrySession:
    """Translate retry task plans into maa-cli execution and back into task outcomes."""

    def __init__(
        self,
        runtime: MaaRuntime,
        diagnostics: Diagnostics,
        *,
        task: str,
        profile_name: str,
        log_level: int,
        generated_run_id: str,
        profile_data: dict[str, object] | None = None,
    ) -> None:
        self.runtime = runtime
        self.diagnostics = diagnostics
        self.task = task
        self.profile_name = profile_name
        self.log_level = log_level
        self.generated_run_id = generated_run_id
        self.profile_data = profile_data
        self._collectors: dict[str, MaaTaskResultCollector] = {}
        self._maacore_log_offsets: dict[str, int] = {}

    @property
    def generated_config_dir(self) -> str:
        return self.runtime.path_references.reference(
            "runtime",
            self.runtime.generated_config_dir / self.generated_run_id,
        )

    def prepare_retry(
        self,
        context: RetryContext,
        task_descriptors: list[MaaTaskDescriptor],
    ) -> CommandSpec:
        task_ids = {item.task_id for item in task_descriptors}
        prepare_messages: list[str] = []
        run_task, run_env = prepare_maa_cli_task(
            self.runtime,
            self.task,
            run_id=self.generated_run_id,
            retry_index=context.retry_index,
            messages=prepare_messages,
            selected_task_ids=task_ids,
            force_enable_selected=True,
            profile_data=self.profile_data,
            profile_name=self.profile_name,
        )
        command = [
            str(self.runtime.maa_bin),
            "run",
            run_task,
            "--batch",
            "--profile",
            self.profile_name,
        ]
        if self.log_level > 0:
            command.extend(["-v"] * self.log_level)

        task_names = [item.name for item in task_descriptors]
        context.add_event(f"开始第 {context.retry_index} 轮运行: {', '.join(task_names)}", tone="info")
        for message in prepare_messages:
            context.add_event(message, tone="info")
        context.configure_log(lambda log: begin_maa_task_sequence(log, _task_descriptor_dicts(task_descriptors)))
        self._collectors[context.retry_id] = MaaTaskResultCollector(task_descriptors)
        self._maacore_log_offsets[context.retry_id] = current_log_offset(maacore_log_source(self.runtime))
        self.runtime.maa_working_dir.mkdir(parents=True, exist_ok=True)
        return CommandSpec(command, cwd=self.runtime.maa_working_dir, env=run_env)

    def consume_raw_line(self, context: RetryContext, stream: str, line: str) -> None:
        collector = self._collectors.get(context.retry_id)
        if collector is not None:
            collector.consume_raw_line(f"maa-cli:{stream}", line)

    def finish_retry(self, context: RetryContext, task_ids: list[str]) -> MaaRetryOutcome:
        collector = self._collectors.pop(context.retry_id, MaaTaskResultCollector([]))
        collector.finish()
        capture = self.diagnostics.capture_file_increment(
            maacore_log_source(self.runtime),
            self._maacore_log_offsets.pop(context.retry_id, 0),
            scope=("maa", "maacore"),
            capture_id=context.retry_id,
        )
        enforce_maa_debug_retention(self.runtime.layout.maa)
        return MaaRetryOutcome(
            task_results=list(collector.results),
            status_by_task_id=collector.status_by_task_id(task_ids),
            generated_config_dir=self.generated_config_dir,
            diagnostic_log_file=capture.log_file,
        )


def prepare_maa_cli_task(
    runtime: MaaRuntime,
    task: str,
    *,
    run_id: str,
    retry_index: int,
    messages: list[str] | None = None,
    selected_task_ids: set[str] | None = None,
    force_enable_selected: bool = False,
    profile_data: dict[str, object] | None = None,
    profile_name: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Resolve the latest source config and materialize one isolated retry config."""
    source = resolve_task_file(runtime, task)
    data = load_task_file(source)
    if selected_task_ids is not None:
        data = select_task_items(data, selected_task_ids, force_enable_selected=force_enable_selected)
    sanitized = prepare_framework_task_config(data, runtime, messages)

    generated_name = f"framework-{run_id}-retry-{retry_index}"
    generated_root = runtime.generated_config_dir / run_id
    generated_tasks = generated_root / "tasks"
    generated_tasks.mkdir(parents=True, exist_ok=True)
    ensure_generated_config_links(runtime, generated_root, skip_names={"profiles"} if profile_data is not None else None)
    if profile_data is not None:
        write_generated_profile(generated_root, profile_name or f"framework-{run_id}", profile_data)

    generated_file = generated_tasks / f"{generated_name}.json"
    write_text_atomic(generated_file, json.dumps(sanitized, ensure_ascii=False, indent=2))

    env = runtime.env()
    env["MAA_CONFIG_DIR"] = str(generated_root)
    return generated_name, env


def select_task_items(data: dict[str, object], selected_task_ids: set[str], *, force_enable_selected: bool) -> dict[str, object]:
    """Filter task list to selected IDs, optionally force-enabling them."""
    selected = dict(data)
    tasks = selected.get("tasks")
    if not isinstance(tasks, list):
        return selected

    selected_tasks: list[object] = []
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            continue
        task_id = task_item_id(task, index)
        if task_id not in selected_task_ids:
            continue
        next_task = dict(task)
        if force_enable_selected:
            params = dict(next_task.get("params")) if isinstance(next_task.get("params"), dict) else {}
            params["enable"] = True
            next_task["params"] = params
        selected_tasks.append(next_task)
    selected["tasks"] = selected_tasks
    return selected


def task_item_id(task: dict[str, object], index: int) -> str:
    metadata = task.get("framework")
    explicit = metadata.get("id") if isinstance(metadata, dict) else None
    if isinstance(explicit, str) and explicit.strip():
        return slugify(explicit) or f"task-{index}"
    task_type = str(task.get("type") or "Task")
    name = task.get("name")
    base = f"{task_type}-{name}" if isinstance(name, str) and name.strip() else task_type
    return slugify(base) or f"task-{index}"


def write_generated_profile(generated_root: Path, profile_name: str, profile_data: dict[str, object]) -> Path:
    profiles_dir = generated_root / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{slugify(profile_name) or 'profile'}.json"
    path = profiles_dir / filename
    write_text_atomic(path, json.dumps(profile_data, ensure_ascii=False, indent=2))
    return path


def resolve_task_file(runtime: MaaRuntime, task: str) -> Path:
    tasks_dir = runtime.config_dir / "tasks"
    return resolve_existing_named_file(tasks_dir, task, suffixes=TASK_SUFFIXES, label="task name")


def load_task_file(path: Path) -> dict[str, object]:
    try:
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".toml":
            return tomllib.loads(content)
        if path.suffix.lower() == ".json":
            loaded = json.loads(content)
            if isinstance(loaded, dict):
                return loaded
            raise CorruptState(f"Task JSON root must be an object: {path}")
    except (UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise CorruptState(f"Cannot parse task config: {path}") from exc
    raise CorruptState(f"Cannot generate maa-cli task from {path.suffix} config: {path}")


def ensure_generated_config_links(runtime: MaaRuntime, generated_root: Path, *, skip_names: set[str] | None = None) -> None:
    runtime.config_dir.mkdir(parents=True, exist_ok=True)
    skip = skip_names or set()
    for source in runtime.config_dir.iterdir():
        if source.name == "tasks" or source.name in skip:
            continue
        target = generated_root / source.name
        if target.exists():
            continue
        target.symlink_to(source, target_is_directory=source.is_dir())


def maacore_log_source(runtime: MaaRuntime) -> Path:
    return runtime.state_home / "maa" / "debug" / "asst.log"


def current_log_offset(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _task_descriptor_dicts(descriptors: list[MaaTaskDescriptor]) -> list[dict[str, str]]:
    return [{"task_id": item.task_id, "source_name": item.source_name, "name": item.name} for item in descriptors]
