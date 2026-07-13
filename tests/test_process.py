from __future__ import annotations

import os
from pathlib import Path
import signal
import sys
import time

from maa_auto_panel.process import run_streaming_process


def test_streaming_process_uses_explicit_working_directory(tmp_path: Path) -> None:
    working_directory = tmp_path / "work"
    working_directory.mkdir()
    output: list[str] = []

    result = run_streaming_process(
        [sys.executable, "-c", "from pathlib import Path; print(Path.cwd())"],
        cwd=working_directory,
        env=os.environ.copy(),
        on_output=output.append,
    )

    assert result.return_code == 0
    assert "".join(output).strip() == str(working_directory)


def test_partial_output_does_not_block_runtime_timeout(tmp_path: Path) -> None:
    output: list[str] = []
    raw_lines: list[tuple[str, str]] = []
    started = time.monotonic()

    result = run_streaming_process(
        [
            sys.executable,
            "-u",
            "-c",
            "import sys, time; sys.stdout.write('partial'); sys.stdout.flush(); time.sleep(30)",
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
        on_output=output.append,
        on_raw_line=lambda stream, line: raw_lines.append((stream, line)),
        runtime_kill_seconds=1,
    )

    assert time.monotonic() - started < 2.5
    assert result.timed_out is True
    assert "".join(output) == "partial"
    assert raw_lines == [("stdout", "partial")]


def test_partial_output_does_not_block_stop_escalation(tmp_path: Path) -> None:
    stop_requested_at = time.monotonic()
    timeout_events: list[str] = []
    child_code = (
        "import signal, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "sys.stderr.write('waiting'); sys.stderr.flush(); time.sleep(30)"
    )

    result = run_streaming_process(
        [sys.executable, "-u", "-c", child_code],
        cwd=tmp_path,
        env=os.environ.copy(),
        on_output=lambda text: None,
        should_stop=lambda: time.monotonic() - stop_requested_at >= 0.25,
        stop_kill_seconds=1,
        on_timeout=lambda level, elapsed: timeout_events.append(level),
    )

    assert time.monotonic() - stop_requested_at < 2.5
    assert result.stopped is True
    assert result.forced is True
    assert result.return_code == -signal.SIGKILL
    assert "stop_kill" in timeout_events


def test_stream_reader_decodes_split_utf8_and_line_endings(tmp_path: Path) -> None:
    chunks: list[str] = []
    raw_lines: list[tuple[str, str]] = []
    combined_log = tmp_path / "combined.log"
    child_code = (
        "import os, sys; "
        "data='甲\\r\\n乙\\r丙'.encode(); "
        "os.write(sys.stdout.fileno(), data[:1]); "
        "os.write(sys.stdout.fileno(), data[1:])"
    )

    result = run_streaming_process(
        [sys.executable, "-u", "-c", child_code],
        cwd=tmp_path,
        env=os.environ.copy(),
        on_output=chunks.append,
        on_raw_line=lambda stream, line: raw_lines.append((stream, line)),
        output_log_file=combined_log,
    )

    assert result.return_code == 0
    assert chunks == ["甲\r\n", "乙\r", "丙"]
    assert raw_lines == [("stdout", "甲"), ("stdout", "乙"), ("stdout", "丙")]
    assert combined_log.read_bytes() == (
        b"[stdout]\n"
        + "甲\r\n".encode()
        + b"[stdout]\n"
        + "乙\r\n".encode()
        + b"[stdout]\n"
        + "丙\n".encode()
    )


def test_oversized_partial_line_is_split_at_bounded_boundary(tmp_path: Path) -> None:
    chunks: list[str] = []
    line_size = 1024 * 1024
    child_code = f"import sys; sys.stdout.write('x' * ({line_size} + 1))"

    result = run_streaming_process(
        [sys.executable, "-u", "-c", child_code],
        cwd=tmp_path,
        env=os.environ.copy(),
        on_output=chunks.append,
    )

    assert result.return_code == 0
    assert chunks == ["x" * line_size + "\n", "x"]
