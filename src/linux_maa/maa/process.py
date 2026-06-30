from __future__ import annotations

import select
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from linux_maa.maa.runtime import MaaRuntime


OutputCallback = Callable[[str], None]
ProcessCallback = Callable[[subprocess.Popen[str]], None]
ShouldStopCallback = Callable[[], bool]
TimeoutCallback = Callable[[str, float], None]
TickCallback = Callable[[], None]


@dataclass(frozen=True)
class MaaCliProcessResult:
    return_code: int | None
    timed_out: bool = False
    stopped: bool = False


def run_maa_cli_process(
    runtime: MaaRuntime,
    cmd: list[str],
    *,
    env: dict[str, str],
    log_file: Path | None,
    on_output: OutputCallback,
    on_process: ProcessCallback | None = None,
    should_stop: ShouldStopCallback | None = None,
    timeout_seconds: int | None = None,
    warning_seconds: int | None = None,
    danger_seconds: int | None = None,
    on_timeout: TimeoutCallback | None = None,
    on_tick: TickCallback | None = None,
) -> MaaCliProcessResult:
    proc = subprocess.Popen(
        cmd,
        cwd=runtime.repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if on_process is not None:
        on_process(proc)

    assert proc.stdout is not None
    start = time.monotonic()
    warned = False
    dangered = False
    timed_out = False
    stopped = False
    log_offset = 0

    while True:
        ready, _, _ = select.select([proc.stdout], [], [], 0.2)
        if ready:
            line = proc.stdout.readline()
            if line:
                on_output(line)
        if log_file is not None:
            log_offset = tail_log_file(log_file, log_offset, on_output)
        if on_tick is not None:
            on_tick()

        elapsed = time.monotonic() - start
        if warning_seconds and not warned and elapsed >= warning_seconds:
            warned = True
            if on_timeout is not None:
                on_timeout("warning", elapsed)
        if danger_seconds and not dangered and elapsed >= danger_seconds:
            dangered = True
            if on_timeout is not None:
                on_timeout("danger", elapsed)
        if timeout_seconds and elapsed >= timeout_seconds and proc.poll() is None:
            timed_out = True
            if on_timeout is not None:
                on_timeout("kill", elapsed)
            _terminate_process(proc)

        if should_stop is not None and should_stop() and proc.poll() is None:
            stopped = True
            _terminate_process(proc)

        if proc.poll() is not None:
            remainder = proc.stdout.read()
            if remainder:
                on_output(remainder)
            if log_file is not None:
                tail_log_file(log_file, log_offset, on_output)
            break

    return MaaCliProcessResult(return_code=proc.wait(), timed_out=timed_out, stopped=stopped)


def tail_log_file(path: Path, offset: int, on_output: OutputCallback) -> int:
    if not path.exists():
        return offset
    try:
        with path.open("rb") as file:
            file.seek(offset)
            data = file.read()
            if not data:
                return offset
            on_output(data.decode("utf-8", errors="replace"))
            return file.tell()
    except OSError as exc:
        on_output(f"读取 maa-cli 日志失败: {exc}\n")
        return offset


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
