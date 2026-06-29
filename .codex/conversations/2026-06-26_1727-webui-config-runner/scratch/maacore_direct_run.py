#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
import tomllib
from pathlib import Path
from typing import Any


MSG_NAMES = {
    0: "InternalError",
    1: "InitFailed",
    2: "ConnectionInfo",
    3: "AllTasksCompleted",
    4: "AsyncCallInfo",
    5: "Destroyed",
    10000: "TaskChainError",
    10001: "TaskChainStart",
    10002: "TaskChainCompleted",
    10003: "TaskChainExtraInfo",
    10004: "TaskChainStopped",
    20000: "SubTaskError",
    20001: "SubTaskStart",
    20002: "SubTaskCompleted",
    20003: "SubTaskExtraInfo",
    20004: "SubTaskStopped",
    30000: "ReportRequest",
}

HIGH_SIGNAL_MSGS = {
    0,
    1,
    2,
    3,
    4,
    5,
    10000,
    10001,
    10002,
    10004,
    20000,
    20001,
    20002,
    20004,
    30000,
}

CHAIN_MSGS = {
    0,
    1,
    2,
    3,
    5,
    10000,
    10001,
    10002,
    10004,
    20000,
    20004,
    30000,
}


def repo_root() -> Path:
    current = Path(__file__).resolve()
    for path in (current, *current.parents):
        if (path / "pyproject.toml").exists() and (path / "runtime" / "maa").exists():
            return path
    raise RuntimeError("Cannot locate repo root")


def b(value: str | Path) -> bytes:
    return str(value).encode("utf-8")


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as file:
        return tomllib.load(file)


def load_core(lib_path: Path) -> ctypes.CDLL:
    return ctypes.CDLL(str(lib_path))


def configure_api(core: ctypes.CDLL) -> None:
    callback_type = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)
    core._callback_type = callback_type

    core.AsstSetUserDir.argtypes = [ctypes.c_char_p]
    core.AsstSetUserDir.restype = ctypes.c_bool

    core.AsstLoadResource.argtypes = [ctypes.c_char_p]
    core.AsstLoadResource.restype = ctypes.c_bool

    core.AsstSetStaticOption.argtypes = [ctypes.c_int, ctypes.c_char_p]
    core.AsstSetStaticOption.restype = ctypes.c_bool

    core.AsstCreateEx.argtypes = [callback_type, ctypes.c_void_p]
    core.AsstCreateEx.restype = ctypes.c_void_p

    core.AsstDestroy.argtypes = [ctypes.c_void_p]
    core.AsstDestroy.restype = None

    core.AsstSetInstanceOption.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
    core.AsstSetInstanceOption.restype = ctypes.c_bool

    core.AsstConnect.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
    core.AsstConnect.restype = ctypes.c_bool

    core.AsstAppendTask.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
    core.AsstAppendTask.restype = ctypes.c_int

    core.AsstStart.argtypes = [ctypes.c_void_p]
    core.AsstStart.restype = ctypes.c_bool

    core.AsstRunning.argtypes = [ctypes.c_void_p]
    core.AsstRunning.restype = ctypes.c_bool

    core.AsstStop.argtypes = [ctypes.c_void_p]
    core.AsstStop.restype = ctypes.c_bool

    core.AsstGetVersion.argtypes = []
    core.AsstGetVersion.restype = ctypes.c_char_p


def callback_printer(event_level: str) -> Any:
    def callback(msg: int, details: bytes | None, custom_arg: object) -> None:
        if event_level == "chain" and msg not in CHAIN_MSGS:
            return
        if event_level == "high" and msg not in HIGH_SIGNAL_MSGS:
            return
        text = details.decode("utf-8", errors="replace") if details else ""
        name = MSG_NAMES.get(msg, str(msg))
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = text
        if isinstance(payload, dict):
            compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        else:
            compact = str(payload)
        print(f"[callback] {msg} {name} {compact}", flush=True)

    return callback


def normalize_task_params(root: Path, task_type: str, params: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(params)
    if task_type == "Infrast" and normalized.get("mode") == 10000 and "filename" in normalized:
        filename = Path(str(normalized["filename"]))
        if not filename.is_absolute():
            filename = root / "runtime" / "maa" / "config" / "infrast" / filename
        normalized["filename"] = str(filename)
    return normalized


def load_tasks(root: Path, task_file: Path, limit: int | None) -> list[tuple[str, dict[str, Any], str]]:
    payload = load_toml(task_file)
    tasks = payload.get("tasks", [])
    result: list[tuple[str, dict[str, Any], str]] = []
    for item in tasks:
        task_type = item["type"]
        name = item.get("name", task_type)
        params = normalize_task_params(root, task_type, item.get("params", {}))
        result.append((task_type, params, name))
        if limit is not None and len(result) >= limit:
            break
    return result


def main() -> int:
    root = repo_root()
    parser = argparse.ArgumentParser(description="Experimental direct MaaCore runner")
    parser.add_argument("--task-file", default="runtime/maa/config/tasks/test.toml")
    parser.add_argument("--profile", default="runtime/maa/config/profiles/default.toml")
    parser.add_argument("--max-seconds", type=float, default=120)
    parser.add_argument("--limit-tasks", type=int, default=None)
    parser.add_argument("--event-level", choices=["chain", "high", "all"], default="high")
    args = parser.parse_args()

    task_file = (root / args.task_file).resolve()
    profile_file = (root / args.profile).resolve()
    profile = load_toml(profile_file)

    runtime = root / "runtime" / "maa"
    data_home = runtime / "data" / "maa"
    lib_dir = data_home / "lib"
    lib_path = lib_dir / "libMaaCore.so"
    resource_base = data_home
    hot_update_base = data_home / "MaaResource"
    user_dir = runtime / "state" / "maa"

    os.environ["LD_LIBRARY_PATH"] = f"{lib_dir}:{os.environ.get('LD_LIBRARY_PATH', '')}"

    core = load_core(lib_path)
    configure_api(core)
    callback = core._callback_type(callback_printer(args.event_level))

    print(f"MaaCore version: {core.AsstGetVersion().decode('utf-8', errors='replace')}")
    print(f"resource_base: {resource_base}")
    print(f"hot_update_base: {hot_update_base}")
    print(f"user_dir: {user_dir}")
    print(f"task_file: {task_file}")

    if not core.AsstSetUserDir(b(user_dir)):
        raise RuntimeError("AsstSetUserDir failed")

    static_options = profile.get("static_options", {})
    if static_options.get("cpu_ocr", False):
        # Observed from maa-cli logs: static option key 1 toggles CPU OCR.
        print("set static cpu_ocr=true")
        if not core.AsstSetStaticOption(1, b("1")):
            raise RuntimeError("AsstSetStaticOption(cpu_ocr) failed")

    if not core.AsstLoadResource(b(resource_base)):
        raise RuntimeError("AsstLoadResource(resource_base) failed")
    if hot_update_base.exists() and not core.AsstLoadResource(b(hot_update_base)):
        raise RuntimeError("AsstLoadResource(hot_update_base) failed")

    handle = core.AsstCreateEx(callback, None)
    if not handle:
        raise RuntimeError("AsstCreateEx failed")

    try:
        instance_options = profile.get("instance_options", {})
        option_map = {
            "touch_mode": (2, lambda value: str(value).lower()),
            "deployment_with_pause": (3, lambda value: "1" if value else "0"),
            "adb_lite_enabled": (4, lambda value: "1" if value else "0"),
            "kill_adb_on_exit": (5, lambda value: "1" if value else "0"),
        }
        for option_name, (key, convert) in option_map.items():
            if option_name not in instance_options:
                continue
            value = convert(instance_options[option_name])
            print(f"set instance {option_name}={value}")
            if not core.AsstSetInstanceOption(handle, key, b(value)):
                raise RuntimeError(f"AsstSetInstanceOption({option_name}) failed")

        connection = profile["connection"]
        print(
            "connect:",
            connection.get("adb_path", "adb"),
            connection["address"],
            connection.get("config", "CompatPOSIXShell"),
        )
        if not core.AsstConnect(
            handle,
            b(connection.get("adb_path", "adb")),
            b(connection["address"]),
            b(connection.get("config", "CompatPOSIXShell")),
        ):
            raise RuntimeError("AsstConnect failed")

        for task_type, params, name in load_tasks(root, task_file, args.limit_tasks):
            params_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
            task_id = core.AsstAppendTask(handle, b(task_type), b(params_json))
            print(f"append task id={task_id} name={name!r} type={task_type} params={params_json}")
            if task_id == 0:
                raise RuntimeError(f"AsstAppendTask failed for {name}/{task_type}")

        if not core.AsstStart(handle):
            raise RuntimeError("AsstStart failed")

        deadline = time.monotonic() + args.max_seconds
        while core.AsstRunning(handle):
            if time.monotonic() > deadline:
                print(f"timeout after {args.max_seconds:g}s, stopping MaaCore")
                core.AsstStop(handle)
                break
            time.sleep(0.5)

        # Give callbacks a short chance to flush after completion/stop.
        time.sleep(1)
        return 0
    finally:
        core.AsstDestroy(handle)


if __name__ == "__main__":
    raise SystemExit(main())
