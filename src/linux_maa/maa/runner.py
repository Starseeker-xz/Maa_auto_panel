from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import tomllib

from linux_maa.android import ADBDevice
from linux_maa.config.tasks import TASK_SUFFIXES, prepare_framework_task_config
from linux_maa.diagnostics import Diagnostics, get_logger
from linux_maa.maa.logs import MaaCliLogTranslator, translate_maa_cli_log
from linux_maa.maa.process import run_maa_cli_process
from linux_maa.settings import DEFAULT_DEVICE_SERIAL, DEFAULT_TARGET_PACKAGE
from linux_maa.maa.runtime import MaaRuntime, find_repo_root
from linux_maa.run_state import RunStateStore
from linux_maa.state import idle_response
from linux_maa.utils import relative_path, resolve_existing_named_file, slugify, write_text_atomic


logger = get_logger(__name__)


def recover_android(adb: ADBDevice, package_name: str, *, force_stop: bool, delay_seconds: float) -> None:
    print("恢复: reconnect adb")
    adb.connect()

    if force_stop:
        print(f"恢复: force-stop {package_name}")
        adb.run(["shell", "am", "force-stop", package_name], check=False, timeout=30)

    print("恢复: 返回 Android 桌面")
    adb.run(["shell", "input", "keyevent", "HOME"], check=False, timeout=30)

    if delay_seconds > 0:
        print(f"恢复: 等待 {delay_seconds:g}s")
        time.sleep(delay_seconds)


def run_maa_task(
    task: str,
    *,
    attempts: int,
    timeout_seconds: int,
    serial: str = DEFAULT_DEVICE_SERIAL,
    package_name: str = DEFAULT_TARGET_PACKAGE,
    adb_path: str = "adb",
    force_stop: bool = True,
    recovery_delay_seconds: float = 5.0,
    profile: str = "default",
    repo_root: Path | None = None,
) -> int:
    runtime = MaaRuntime(find_repo_root(repo_root))
    runtime.run_log_dir.mkdir(parents=True, exist_ok=True)

    adb = ADBDevice(serial, adb_path)
    started_at = datetime.now().strftime("%Y%m%d-%H%M%S")

    for attempt in range(1, attempts + 1):
        log_file = runtime.run_log_dir / f"{started_at}-{task}-attempt-{attempt}.log"
        run_task, run_env = prepare_maa_cli_task(runtime, task, run_id=f"cli-{started_at}", attempt=attempt)
        cmd = [
            str(runtime.maa_bin),
            "run",
            run_task,
            "--batch",
            "--profile",
            profile,
            f"--log-file={log_file}",
        ]

        print(f"尝试 {attempt}/{attempts}: {' '.join(cmd)}")
        try:
            proc = subprocess.run(
                cmd,
                cwd=runtime.repo_root,
                env=run_env,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                encoding="utf-8",
                errors="replace",
            )
            if proc.stdout:
                print(proc.stdout, end="")
            if proc.stderr:
                print(proc.stderr, end="")

            if proc.returncode == 0:
                print(f"任务 {task} 成功，日志: {log_file}")
                return 0

            print(f"任务 {task} 失败，退出码 {proc.returncode}，日志: {log_file}")
        except subprocess.TimeoutExpired as exc:
            if exc.stdout:
                print(exc.stdout, end="" if exc.stdout.endswith("\n") else "\n")
            if exc.stderr:
                print(exc.stderr, end="" if exc.stderr.endswith("\n") else "\n")
            print(f"任务 {task} 超时 {timeout_seconds}s，日志: {log_file}")

        if attempt < attempts:
            recover_android(adb, package_name, force_stop=force_stop, delay_seconds=recovery_delay_seconds)

    print(f"任务 {task} 在 {attempts} 次尝试后仍失败")
    return 1


def prepare_maa_cli_task(
    runtime: MaaRuntime,
    task: str,
    *,
    run_id: str,
    attempt: int,
    messages: list[str] | None = None,
    selected_task_ids: set[str] | None = None,
    force_enable_selected: bool = False,
    profile_data: dict[str, object] | None = None,
    profile_name: str | None = None,
) -> tuple[str, dict[str, str]]:
    source = resolve_task_file(runtime, task)
    data = load_task_file(source)
    if selected_task_ids is not None:
        data = select_task_items(data, selected_task_ids, force_enable_selected=force_enable_selected)
    sanitized = prepare_framework_task_config(data, runtime, messages)

    generated_name = f"linux-maa-{run_id}-attempt-{attempt}"
    generated_root = runtime.generated_config_dir / run_id
    generated_tasks = generated_root / "tasks"
    generated_tasks.mkdir(parents=True, exist_ok=True)
    ensure_generated_config_links(runtime, generated_root, skip_names={"profiles"} if profile_data is not None else None)
    if profile_data is not None:
        write_generated_profile(generated_root, profile_name or f"linux-maa-{run_id}", profile_data)

    generated_file = generated_tasks / f"{generated_name}.json"
    write_text_atomic(generated_file, json.dumps(sanitized, ensure_ascii=False, indent=2))

    env = runtime.env()
    env["MAA_CONFIG_DIR"] = str(generated_root)
    return generated_name, env


def select_task_items(data: dict[str, object], selected_task_ids: set[str], *, force_enable_selected: bool) -> dict[str, object]:
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
    metadata = task.get("linux_maa")
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
    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".toml":
        return tomllib.loads(content)
    if path.suffix.lower() == ".json":
        loaded = json.loads(content)
        if isinstance(loaded, dict):
            return loaded
        raise ValueError("Task JSON root must be an object")
    raise ValueError(f"Cannot generate maa-cli task from {path.suffix} config yet")


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


@dataclass(frozen=True)
class MaaRunRequest:
    task: str
    profile: str = "default"
    log_level: int = 1


@dataclass
class MaaRunState:
    id: str
    task: str
    profile: str
    status: str
    created_at: str
    updated_at: str
    log_level: int
    return_code: int | None = None
    log_file: str | None = None
    log_files: dict[str, str] = field(default_factory=dict)
    maacore_log_file: str | None = None
    maacore_log_start: int = 0
    lines: deque[str] = field(default_factory=lambda: deque(maxlen=2000))
    log_translator: MaaCliLogTranslator = field(default_factory=MaaCliLogTranslator)
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    thread: threading.Thread | None = field(default=None, repr=False)

    def to_dict(self, *, include_logs: bool = True) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "task": self.task,
            "profile": self.profile,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "log_level": self.log_level,
            "return_code": self.return_code,
            "log_file": self.log_file,
            "log_files": dict(self.log_files),
            "maacore_log_file": self.maacore_log_file,
        }
        if include_logs:
            data.update(
                {
                    "output": list(self.lines),
                    "task_results": self.log_translator.task_results(),
                    "log_entries": self.log_translator.entries(),
                }
            )
        return data


class MaaRunManager:
    def __init__(
        self,
        runtime: MaaRuntime,
        run_state: RunStateStore | None = None,
        diagnostics: Diagnostics | None = None,
    ) -> None:
        self.runtime = runtime
        self.run_state = run_state or RunStateStore(runtime)
        self.diagnostics = diagnostics or Diagnostics(runtime)
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._version = 0
        self._runs: dict[str, MaaRunState] = {}
        self._current_run_id: str | None = None

    def start(self, request: MaaRunRequest) -> MaaRunState:
        with self._lock:
            current = self._runs.get(self._current_run_id or "")
            if current and current.status == "running":
                raise RuntimeError(f"Run already active: {current.id}")

            now = datetime.now().isoformat(timespec="seconds")
            run_id = uuid.uuid4().hex[:12]
            state = MaaRunState(
                id=run_id,
                task=request.task,
                profile=request.profile,
                status="running",
                created_at=now,
                updated_at=now,
                log_level=request.log_level,
            )
            state.log_file = self.diagnostics.maa_cli_log_file(run_id)
            state.log_files = self.diagnostics.maa_cli_log_files(run_id)
            state.maacore_log_start = self.diagnostics.maacore_log_offset()
            self.run_state.create_manual_run(
                run_id=run_id,
                task=request.task,
                profile=request.profile,
                log_file=state.log_file,
                log_files=state.log_files,
                event_log_file=self.diagnostics.event_log_file(run_id),
            )
            logger.info("manual run started run_id=%s task=%s profile=%s log_level=%s", run_id, request.task, request.profile, request.log_level)
            self._runs[run_id] = state
            self._current_run_id = run_id
            self._notify_locked()

        thread = threading.Thread(target=self._run, args=(state,), daemon=True)
        state.thread = thread
        thread.start()
        return state

    def wait_for_change(self, last_version: int, timeout: float | None = None) -> int:
        with self._condition:
            if self._version == last_version:
                self._condition.wait(timeout)
            return self._version

    def current(self) -> MaaRunState | None:
        with self._lock:
            return self._runs.get(self._current_run_id or "")

    def current_response(self, *, include_logs: bool = True) -> dict[str, object]:
        with self._lock:
            state = self._runs.get(self._current_run_id or "")
            version = self._version
            payload = state.to_dict(include_logs=include_logs) if state is not None else idle_response()
        payload["stream_version"] = version
        return payload

    def get(self, run_id: str) -> MaaRunState | None:
        with self._lock:
            return self._runs.get(run_id)

    def stop(self, run_id: str) -> MaaRunState:
        state = self.get(run_id)
        if state is None:
            raise KeyError(run_id)
        with self._lock:
            if state.process and state.process.poll() is None:
                self.diagnostics.append_run_event(state.id, "manual", "framework", "收到停止请求，正在终止 maa-cli...", tone="warning")
                logger.warning("manual run stop requested run_id=%s", state.id)
                state.lines.append(
                    state.log_translator.add_event(
                        "收到停止请求，正在终止 maa-cli...",
                        time=datetime.now().strftime("%H:%M:%S"),
                        tone="warning",
                    )
                )
                state.process.terminate()
                state.status = "stopping"
                state.updated_at = datetime.now().isoformat(timespec="seconds")
                self._notify_locked()
        return state

    def _append(self, state: MaaRunState, line: str) -> None:
        with self._lock:
            state.lines.append(line)
            state.updated_at = datetime.now().isoformat(timespec="seconds")
            self._notify_locked()

    def _append_maa_log(self, state: MaaRunState, text: str, stream: str = "output") -> None:
        self.diagnostics.append_maa_cli_output(state.id, stream, text)
        translated = state.log_translator.translate(text)
        if translated:
            self._append(state, translated)

    def _flush_maa_log(self, state: MaaRunState) -> None:
        translated = state.log_translator.flush()
        if translated:
            self._append(state, translated)

    def _append_framework_log(self, state: MaaRunState, text: str) -> None:
        self.diagnostics.append_run_event(state.id, "manual", "framework", text)
        logger.info("manual run event run_id=%s text=%s", state.id, text)
        translated = state.log_translator.add_event(text, time=datetime.now().strftime("%H:%M:%S"), tone="info")
        self._append(state, translated)

    def _set_done(self, state: MaaRunState, status: str, return_code: int | None) -> None:
        with self._lock:
            state.status = status
            state.return_code = return_code
            state.updated_at = datetime.now().isoformat(timespec="seconds")
            state.process = None
            self._notify_locked()
        maacore_log_file = self.diagnostics.capture_maacore_log(state.id, state.maacore_log_start)
        if maacore_log_file is not None:
            state.maacore_log_file = maacore_log_file
        self.run_state.finish_generic_run(
            state.id,
            status=status,
            return_code=return_code,
            maacore_log_file=maacore_log_file,
            summary={
                "task_results": state.log_translator.task_results(),
                "generated_config_dir": relative_path(self.runtime.generated_config_dir / state.id, self.runtime.repo_root),
            },
        )
        self.run_state.enforce_retention()
        self.diagnostics.enforce_retention()
        logger.info("manual run finished run_id=%s status=%s return_code=%s maacore_log_file=%s", state.id, status, return_code, maacore_log_file)

    def _run(self, state: MaaRunState) -> None:
        prepare_messages: list[str] = []
        run_task, run_env = prepare_maa_cli_task(self.runtime, state.task, run_id=state.id, attempt=1, messages=prepare_messages)
        cmd = [
            str(self.runtime.maa_bin),
            "run",
            run_task,
            "--batch",
            "--profile",
            state.profile,
        ]
        if state.log_level > 0:
            cmd.extend(["-v"] * state.log_level)
        self._append_framework_log(state, f"运行: {state.task}")
        for message in prepare_messages:
            self._append_framework_log(state, message)

        try:
            return_code = self._run_process(state, cmd, run_env)
        except Exception as exc:
            self._append_framework_log(state, f"启动 maa-cli 失败: {exc}")
            logger.exception("manual run process start failed run_id=%s", state.id)
            self._set_done(state, "failed", None)
            return

        if return_code == 0:
            self._append_framework_log(state, "maa-cli 退出码: 0")
            self._set_done(state, "succeeded", 0)
            return

        if state.status == "stopping":
            self._append_framework_log(state, f"maa-cli 退出码: {return_code}")
            self._set_done(state, "stopped", return_code)
            return

        self._append_framework_log(state, f"maa-cli 退出码: {return_code}")
        self._set_done(state, "failed", return_code)

    def _run_process(self, state: MaaRunState, cmd: list[str], env: dict[str, str]) -> int | None:
        result = run_maa_cli_process(
            self.runtime,
            cmd,
            env=env,
            on_output=lambda text: None,
            on_stream_output=lambda stream, text: self._append_maa_log(state, text, stream),
            on_process=lambda proc: self._set_process(state, proc),
        )
        self._flush_maa_log(state)
        return result.return_code

    def _set_process(self, state: MaaRunState, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            state.process = proc

    def _notify_locked(self) -> None:
        self._version += 1
        self._condition.notify_all()
