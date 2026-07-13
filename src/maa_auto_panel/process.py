from __future__ import annotations

import codecs
from contextlib import nullcontext
import os
import select
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO, cast

OutputCallback = Callable[[str], None]
StreamOutputCallback = Callable[[str, str], None]
RawLineCallback = Callable[[str, str], None]
ProcessCallback = Callable[[subprocess.Popen[str]], None]
ShouldStopCallback = Callable[[], bool]
TimeoutCallback = Callable[[str, float], None]
TickCallback = Callable[[], None]


_READ_CHUNK_SIZE = 64 * 1024
_MAX_PARTIAL_LINE_CHARS = 1024 * 1024


@dataclass(frozen=True)
class StreamingProcessResult:
    """Immutable result: return code, timeout flag, and stopped flag from a streaming subprocess run."""
    return_code: int | None
    timed_out: bool = False
    stopped: bool = False
    forced: bool = False


def run_streaming_process(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    on_output: OutputCallback,
    on_stream_output: StreamOutputCallback | None = None,
    on_raw_line: RawLineCallback | None = None,
    output_log_file: Path | None = None,
    on_process: ProcessCallback | None = None,
    should_stop: ShouldStopCallback | None = None,
    should_force_stop: ShouldStopCallback | None = None,
    runtime_warning_seconds: int | None = None,
    runtime_kill_seconds: int | None = None,
    no_output_warning_seconds: int | None = None,
    no_output_kill_seconds: int | None = None,
    stop_warning_seconds: int | None = None,
    stop_kill_seconds: int | None = None,
    on_timeout: TimeoutCallback | None = None,
    on_tick: TickCallback | None = None,
) -> StreamingProcessResult:
    """Run subprocess with streaming output, hang/runtime timeouts, graceful stop, and force stop."""
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    if on_process is not None:
        on_process(cast(subprocess.Popen[str], proc))

    assert proc.stdout is not None
    assert proc.stderr is not None
    os.set_blocking(proc.stdout.fileno(), False)
    os.set_blocking(proc.stderr.fileno(), False)
    streams = {
        proc.stdout.fileno(): _StreamReader("stdout"),
        proc.stderr.fileno(): _StreamReader("stderr"),
    }
    start = time.monotonic()
    last_output = start
    runtime_warned = False
    no_output_warned = False
    stop_warned = False
    stop_sent = False
    stop_started: float | None = None
    timed_out = False
    stopped = False
    forced = False

    log_context = output_log_file.open("a", encoding="utf-8", errors="replace") if output_log_file is not None else nullcontext(None)
    with log_context as log_sink:
        while True:
            now = time.monotonic()
            if streams:
                ready, _, _ = select.select(list(streams), [], [], 0.2)
            else:
                time.sleep(0.2)
                ready = []
            for fd in ready:
                reader = streams[fd]
                try:
                    data = os.read(fd, _READ_CHUNK_SIZE)
                except BlockingIOError:
                    continue
                if data:
                    reader.feed(data, on_output, on_stream_output, on_raw_line, log_sink)
                    last_output = time.monotonic()
                    no_output_warned = False
                else:
                    reader.finish(on_output, on_stream_output, on_raw_line, log_sink)
                    streams.pop(fd, None)
            if on_tick is not None:
                on_tick()

            now = time.monotonic()
            elapsed = now - start
            silent_elapsed = now - last_output
            if runtime_warning_seconds and not runtime_warned and elapsed >= runtime_warning_seconds:
                runtime_warned = True
                if on_timeout is not None:
                    on_timeout("runtime_warning", elapsed)
            if runtime_kill_seconds and elapsed >= runtime_kill_seconds and proc.poll() is None:
                timed_out = True
                if on_timeout is not None:
                    on_timeout("runtime_kill", elapsed)
                _terminate_process(proc)
            if no_output_warning_seconds and not no_output_warned and silent_elapsed >= no_output_warning_seconds:
                no_output_warned = True
                if on_timeout is not None:
                    on_timeout("no_output_warning", silent_elapsed)
            if no_output_kill_seconds and silent_elapsed >= no_output_kill_seconds and proc.poll() is None:
                timed_out = True
                if on_timeout is not None:
                    on_timeout("no_output_kill", silent_elapsed)
                _terminate_process(proc)

            if should_stop is not None and should_stop() and proc.poll() is None and not stop_sent:
                stopped = True
                stop_sent = True
                stop_started = time.monotonic()
                terminate_process_group(proc)
            if stop_sent and stop_started is not None and proc.poll() is None:
                stop_elapsed = time.monotonic() - stop_started
                if stop_warning_seconds and not stop_warned and stop_elapsed >= stop_warning_seconds:
                    stop_warned = True
                    if on_timeout is not None:
                        on_timeout("stop_warning", stop_elapsed)
                if stop_kill_seconds and stop_elapsed >= stop_kill_seconds:
                    forced = True
                    if on_timeout is not None:
                        on_timeout("stop_kill", stop_elapsed)
                    force_kill_process_group(proc)
            if should_force_stop is not None and should_force_stop() and proc.poll() is None:
                forced = True
                if on_timeout is not None:
                    on_timeout("force_kill", time.monotonic() - start)
                force_kill_process_group(proc)

            if proc.poll() is not None and not streams:
                break

    return StreamingProcessResult(return_code=proc.wait(), timed_out=timed_out, stopped=stopped, forced=forced)


class _StreamReader:
    def __init__(self, stream: str) -> None:
        self.stream = stream
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.partial_line = ""

    def feed(
        self,
        data: bytes,
        on_output: OutputCallback,
        on_stream_output: StreamOutputCallback | None,
        on_raw_line: RawLineCallback | None,
        log_sink: TextIO | None,
    ) -> None:
        self._accept_text(self.decoder.decode(data), on_output, on_stream_output, on_raw_line, log_sink)

    def finish(
        self,
        on_output: OutputCallback,
        on_stream_output: StreamOutputCallback | None,
        on_raw_line: RawLineCallback | None,
        log_sink: TextIO | None,
    ) -> None:
        self._accept_text(self.decoder.decode(b"", final=True), on_output, on_stream_output, on_raw_line, log_sink)
        if self.partial_line.endswith("\r"):
            _emit_record(
                self.partial_line[:-1], "\r", self.stream, on_output, on_stream_output, on_raw_line, log_sink
            )
            self.partial_line = ""
        if self.partial_line:
            _emit_record(self.partial_line, "", self.stream, on_output, on_stream_output, on_raw_line, log_sink)
            self.partial_line = ""

    def _accept_text(
        self,
        text: str,
        on_output: OutputCallback,
        on_stream_output: StreamOutputCallback | None,
        on_raw_line: RawLineCallback | None,
        log_sink: TextIO | None,
    ) -> None:
        if not text:
            return
        self.partial_line += text
        while self.partial_line:
            newline_at = _newline_index(self.partial_line)
            if newline_at is not None:
                line_end, delimiter_end = newline_at
                _emit_record(
                    self.partial_line[:line_end],
                    self.partial_line[line_end:delimiter_end],
                    self.stream,
                    on_output,
                    on_stream_output,
                    on_raw_line,
                    log_sink,
                )
                self.partial_line = self.partial_line[delimiter_end:]
                continue
            if len(self.partial_line) > _MAX_PARTIAL_LINE_CHARS:
                _emit_record(
                    self.partial_line[:_MAX_PARTIAL_LINE_CHARS],
                    "\n",
                    self.stream,
                    on_output,
                    on_stream_output,
                    on_raw_line,
                    log_sink,
                )
                self.partial_line = self.partial_line[_MAX_PARTIAL_LINE_CHARS:]
                continue
            break


def _newline_index(text: str) -> tuple[int, int] | None:
    cr = text.find("\r")
    lf = text.find("\n")
    indexes = [index for index in (cr, lf) if index >= 0]
    if not indexes:
        return None
    line_end = min(indexes)
    if text[line_end] == "\r" and line_end + 1 == len(text):
        return None
    delimiter_end = line_end + 2 if text.startswith("\r\n", line_end) else line_end + 1
    return line_end, delimiter_end


def _emit_record(
    text: str,
    ending: str,
    stream: str,
    on_output: OutputCallback,
    on_stream_output: StreamOutputCallback | None,
    on_raw_line: RawLineCallback | None,
    log_sink: TextIO | None = None,
) -> None:
    record = text + ending
    if log_sink is not None:
        log_sink.write(f"[{stream}]\n{record}")
        if not ending.endswith("\n"):
            log_sink.write("\n")
        log_sink.flush()
    if on_stream_output is not None:
        on_stream_output(stream, record)
    if on_raw_line is not None:
        on_raw_line(stream, text)
    on_output(record)


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    terminate_process_group(proc)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        force_kill_process_group(proc)


def terminate_process_group(proc: subprocess.Popen[str] | None) -> None:
    _signal_process_group(proc, signal.SIGTERM)


def force_kill_process_group(proc: subprocess.Popen[str] | None) -> None:
    _signal_process_group(proc, signal.SIGKILL)


def _signal_process_group(proc: subprocess.Popen[str] | None, sig: signal.Signals) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except ProcessLookupError:
        return
    except OSError:
        try:
            proc.send_signal(sig)
        except ProcessLookupError:
            pass
