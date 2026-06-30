from __future__ import annotations

import json
import re
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
from linux_maa.maa.logs import MaaCliLogTranslator, translate_maa_cli_log
from linux_maa.maa.process import run_maa_cli_process
from linux_maa.settings import DEFAULT_DEVICE_SERIAL, DEFAULT_TARGET_PACKAGE
from linux_maa.maa.runtime import MaaRuntime, find_repo_root


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
    generated_file.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")

    env = runtime.env()
    env["MAA_CONFIG_DIR"] = str(generated_root)
    return generated_name, env


def select_task_items(data: dict[str, object], selected_task_ids: set[str], *, force_enable_selected: bool) -> dict[str, object]:
    selected = dict(data)
    tasks = selected.get("tasks")
    if not isinstance(tasks, list):
        return selected

    selected_tasks: list[object] = []
    seen: set[str] = set()
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            continue
        task_id = task_item_id(task, index)
        if task_id not in selected_task_ids:
            continue
        seen.add(task_id)
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
        return _slug(explicit) or f"task-{index}"
    task_type = str(task.get("type") or "Task")
    name = task.get("name")
    base = f"{task_type}-{name}" if isinstance(name, str) and name.strip() else task_type
    return _slug(base) or f"task-{index}"


def write_generated_profile(generated_root: Path, profile_name: str, profile_data: dict[str, object]) -> Path:
    profiles_dir = generated_root / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_slug(profile_name) or 'profile'}.json"
    path = profiles_dir / filename
    path.write_text(json.dumps(profile_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def resolve_task_file(runtime: MaaRuntime, task: str) -> Path:
    requested = Path(task)
    if requested.name != task or task in {"", ".", ".."}:
        raise ValueError("Invalid task name")

    tasks_dir = runtime.config_dir / "tasks"
    if requested.suffix:
        candidates = [tasks_dir / requested.name]
    else:
        candidates = [tasks_dir / f"{task}{suffix}" for suffix in TASK_SUFFIXES]

    for candidate in candidates:
        try:
            candidate.relative_to(tasks_dir)
        except ValueError as exc:
            raise ValueError("Invalid task path") from exc
        if candidate.is_file() and candidate.suffix.lower() in TASK_SUFFIXES:
            return candidate
    raise FileNotFoundError(task)


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


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-").lower()[:64]


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
    lines: deque[str] = field(default_factory=lambda: deque(maxlen=2000))
    log_translator: MaaCliLogTranslator = field(default_factory=MaaCliLogTranslator)
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    thread: threading.Thread | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "task": self.task,
            "profile": self.profile,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "log_level": self.log_level,
            "return_code": self.return_code,
            "log_file": self.log_file,
            "output": list(self.lines),
            "task_results": self.log_translator.task_results(),
            "log_entries": self.log_translator.entries(),
        }


class MaaRunManager:
    def __init__(self, runtime: MaaRuntime) -> None:
        self.runtime = runtime
        self._lock = threading.Lock()
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
            self._runs[run_id] = state
            self._current_run_id = run_id

        thread = threading.Thread(target=self._run, args=(state,), daemon=True)
        state.thread = thread
        thread.start()
        return state

    def current(self) -> MaaRunState | None:
        with self._lock:
            return self._runs.get(self._current_run_id or "")

    def get(self, run_id: str) -> MaaRunState | None:
        with self._lock:
            return self._runs.get(run_id)

    def stop(self, run_id: str) -> MaaRunState:
        state = self.get(run_id)
        if state is None:
            raise KeyError(run_id)
        with self._lock:
            if state.process and state.process.poll() is None:
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
        return state

    def _append(self, state: MaaRunState, line: str) -> None:
        with self._lock:
            state.lines.append(line)
            state.updated_at = datetime.now().isoformat(timespec="seconds")

    def _append_maa_log(self, state: MaaRunState, text: str) -> None:
        translated = state.log_translator.translate(text)
        if translated:
            self._append(state, translated)

    def _flush_maa_log(self, state: MaaRunState) -> None:
        translated = state.log_translator.flush()
        if translated:
            self._append(state, translated)

    def _append_framework_log(self, state: MaaRunState, text: str) -> None:
        translated = state.log_translator.add_event(text, time=datetime.now().strftime("%H:%M:%S"), tone="info")
        self._append(state, translated)

    def _set_done(self, state: MaaRunState, status: str, return_code: int | None) -> None:
        with self._lock:
            state.status = status
            state.return_code = return_code
            state.updated_at = datetime.now().isoformat(timespec="seconds")
            state.process = None

    def _run(self, state: MaaRunState) -> None:
        self.runtime.run_log_dir.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now().strftime("%Y%m%d-%H%M%S")

        log_file = self.runtime.run_log_dir / f"{started_at}-{state.task}-webui.log"
        with self._lock:
            state.log_file = str(log_file.relative_to(self.runtime.repo_root)) if state.log_level > 0 else None
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
            cmd.append(f"--log-file={log_file}")
            cmd.extend(["-v"] * state.log_level)
        self._append(state, f"\n运行: {state.task}\n")
        for message in prepare_messages:
            self._append_framework_log(state, message)

        try:
            return_code = self._run_process(state, cmd, log_file if state.log_level > 0 else None, run_env)
        except Exception as exc:
            self._append(state, f"启动 maa-cli 失败: {exc}\n")
            self._set_done(state, "failed", None)
            return

        if return_code == 0:
            self._append(state, "\nmaa-cli 退出码: 0\n")
            self._set_done(state, "succeeded", 0)
            return

        if state.status == "stopping":
            self._append(state, f"\nmaa-cli 退出码: {return_code}\n")
            self._set_done(state, "stopped", return_code)
            return

        self._append(state, f"\nmaa-cli 退出码: {return_code}\n")
        self._set_done(state, "failed", return_code)

    def _run_process(self, state: MaaRunState, cmd: list[str], log_file: Path | None, env: dict[str, str]) -> int | None:
        result = run_maa_cli_process(
            self.runtime,
            cmd,
            env=env,
            log_file=log_file,
            on_output=lambda text: self._append_maa_log(state, text),
            on_process=lambda proc: self._set_process(state, proc),
        )
        self._flush_maa_log(state)
        return result.return_code

    def _set_process(self, state: MaaRunState, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            state.process = proc
