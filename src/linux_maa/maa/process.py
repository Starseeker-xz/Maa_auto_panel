from __future__ import annotations

from contextlib import nullcontext
import select
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO

from linux_maa.maa.runtime import MaaRuntime


OutputCallback = Callable[[str], None]
StreamOutputCallback = Callable[[str, str], None]
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
    on_output: OutputCallback,
    on_stream_output: StreamOutputCallback | None = None,
    output_log_file: Path | None = None,
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
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if on_process is not None:
        on_process(proc)

    assert proc.stdout is not None
    assert proc.stderr is not None
    streams = {
        proc.stdout: "stdout",
        proc.stderr: "stderr",
    }
    start = time.monotonic()
    warned = False
    dangered = False
    timed_out = False
    stopped = False

    log_context = output_log_file.open("a", encoding="utf-8", errors="replace") if output_log_file is not None else nullcontext(None)
    with log_context as log_sink:
        while True:
            if streams:
                ready, _, _ = select.select(list(streams), [], [], 0.2)
            else:
                time.sleep(0.2)
                ready = []
            for pipe in ready:
                line = pipe.readline()
                if line:
                    _emit_output(line, streams[pipe], on_output, on_stream_output, log_sink)
                else:
                    streams.pop(pipe, None)
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
                for pipe, stream in streams.items():
                    remainder = pipe.read()
                    if remainder:
                        _emit_output(remainder, stream, on_output, on_stream_output, log_sink)
                break

    return MaaCliProcessResult(return_code=proc.wait(), timed_out=timed_out, stopped=stopped)


def _emit_output(
    text: str,
    stream: str,
    on_output: OutputCallback,
    on_stream_output: StreamOutputCallback | None,
    log_sink: TextIO | None = None,
) -> None:
    if not text:
        return
    if log_sink is not None:
        log_sink.write(f"[{stream}]\n{text}")
        if not text.endswith("\n"):
            log_sink.write("\n")
        log_sink.flush()
    if on_stream_output is not None:
        on_stream_output(stream, text)
    on_output(text)


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
