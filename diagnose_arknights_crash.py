#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from typing import List, Optional, Tuple

DEFAULT_DEVICE_SERIAL = "192.168.5.151:5555"
DEFAULT_TARGET_PKG = "com.hypergryph.arknights.bilibili"


def run_cmd(cmd: List[str], timeout: Optional[int] = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=check,
    )


def adb(serial: str, args: List[str], timeout: Optional[int] = None, check: bool = True) -> subprocess.CompletedProcess:
    return run_cmd(["adb", "-s", serial] + args, timeout=timeout, check=check)


def connect_device(serial: str) -> None:
    if ":" in serial:
        run_cmd(["adb", "connect", serial], check=False)


def is_device_online(serial: str) -> bool:
    proc = run_cmd(["adb", "devices"], check=False)
    for line in proc.stdout.splitlines():
        if not line.strip() or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0] == serial and parts[1] == "device":
            return True
    return False


def is_package_installed(serial: str, pkg: str) -> bool:
    proc = adb(serial, ["shell", "pm", "path", pkg], check=False)
    return "package:" in proc.stdout


def clear_logcat(serial: str) -> None:
    adb(serial, ["logcat", "-c"], check=False)


def get_main_activity(serial: str, pkg: str) -> Optional[str]:
    proc = adb(serial, ["shell", "cmd", "package", "resolve-activity", "--brief", pkg], check=False)
    lines = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
    if not lines:
        return None

    candidate = lines[-1]
    if "/" in candidate and candidate.startswith(pkg):
        return candidate
    return None


def launch_app(serial: str, pkg: str) -> None:
    main_activity = get_main_activity(serial, pkg)
    if main_activity:
        adb(serial, ["shell", "am", "start", "-W", "-n", main_activity], check=False)
    else:
        # Fallback: ask system to launch the package's default activity.
        adb(serial, ["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"], check=False)


def get_pid(serial: str, pkg: str) -> Optional[int]:
    proc = adb(serial, ["shell", "pidof", "-s", pkg], check=False)
    text = proc.stdout.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def dump_logcat(serial: str) -> str:
    proc = adb(serial, ["logcat", "-d", "-v", "threadtime"], check=False)
    return proc.stdout


def detect_crash_sections(lines: List[str], pkg: str, pid: Optional[int]) -> Tuple[List[str], List[str]]:
    markers = [
        "FATAL EXCEPTION",
        "Fatal signal",
        "am_crash",
        "ANR in",
        "Process " + pkg + " has died",
        "Force finishing activity",
    ]

    hit_indices: List[int] = []
    for idx, line in enumerate(lines):
        if any(marker in line for marker in markers):
            hit_indices.append(idx)
            continue

        # AndroidRuntime lines are useful only when they are for this package.
        if "AndroidRuntime" in line and pkg in line:
            hit_indices.append(idx)
            continue

        if pid is not None and re.search(rf"\b{pid}\b", line) and ("Fatal signal" in line or "crash" in line.lower()):
            hit_indices.append(idx)

    sections: List[str] = []
    seen = set()
    for idx in hit_indices:
        start = max(0, idx - 15)
        end = min(len(lines), idx + 40)
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        block = "\n".join(lines[start:end])
        sections.append(block)

    verdict: List[str] = []
    all_text = "\n".join(lines)

    if "FATAL EXCEPTION" in all_text:
        verdict.append("Detected Java/Kotlin crash (FATAL EXCEPTION).")
    if "Fatal signal" in all_text:
        verdict.append("Detected native crash (Fatal signal, usually C/C++/NDK layer).")
    if f"ANR in {pkg}" in all_text or "ANR in" in all_text:
        verdict.append("Detected ANR (app not responding).")
    if not verdict:
        verdict.append("No explicit crash marker found in current logcat dump.")

    return verdict, sections


def save_outputs(base_dir: str, pkg: str, serial: str, log_text: str, verdict: List[str], sections: List[str], pid_before: Optional[int], pid_after: Optional[int]) -> Tuple[str, str]:
    os.makedirs(base_dir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_pkg = pkg.replace(".", "_")

    log_file = os.path.join(base_dir, f"crashlog_{safe_pkg}_{stamp}.log")
    summary_file = os.path.join(base_dir, f"crash_summary_{safe_pkg}_{stamp}.json")

    with open(log_file, "w", encoding="utf-8") as f:
        f.write(log_text)

    payload = {
        "timestamp": stamp,
        "device_serial": serial,
        "package": pkg,
        "pid_before_launch": pid_before,
        "pid_after_wait": pid_after,
        "verdict": verdict,
        "sections": sections,
    }

    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return log_file, summary_file


def get_exit_info(serial: str, pkg: str) -> str:
    # Android 11+ usually supports this and records historical process exits/crashes.
    proc = adb(serial, ["shell", "dumpsys", "activity", "exit-info", pkg], check=False)
    return proc.stdout


def save_exit_info(base_dir: str, pkg: str, exit_info: str) -> Optional[str]:
    if not exit_info.strip():
        return None
    os.makedirs(base_dir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_pkg = pkg.replace(".", "_")
    path = os.path.join(base_dir, f"exit_info_{safe_pkg}_{stamp}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(exit_info)
    return path


def extract_suspicious_exit_info(exit_info: str) -> List[str]:
    out: List[str] = []
    if not exit_info.strip():
        return out

    lines = exit_info.splitlines()
    interesting = ("(CRASH)", "(ANR)", "(NATIVE CRASH)", "(LOW_MEMORY)")
    for idx, line in enumerate(lines):
        if "reason=" in line and any(tag in line for tag in interesting):
            ts = ""
            process = ""
            for back in range(max(0, idx - 3), idx + 1):
                if "timestamp=" in lines[back]:
                    ts = lines[back].strip()
                if "process=" in lines[back]:
                    process = lines[back].strip()
            out.append(f"{ts} | {process} | {line.strip()}")
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose Android app crash reason via adb logcat.")
    parser.add_argument("--serial", default=DEFAULT_DEVICE_SERIAL, help="adb device serial")
    parser.add_argument("--pkg", default=DEFAULT_TARGET_PKG, help="target package name")
    parser.add_argument("--wait", type=int, default=20, help="seconds to wait after launch")
    parser.add_argument("--out", default="downloads", help="output folder for log and summary")
    parser.add_argument("--no-clear", action="store_true", help="do not clear logcat before collecting")
    parser.add_argument("--history-only", action="store_true", help="do not launch app; only collect historical traces")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    serial = args.serial
    pkg = args.pkg

    print(f"[1/6] Connecting device: {serial}")
    connect_device(serial)

    print("[2/6] Checking device state")
    if not is_device_online(serial):
        print("ERROR: Device not online in adb devices.")
        return 2

    print(f"[3/6] Checking package installed: {pkg}")
    if not is_package_installed(serial, pkg):
        print("ERROR: Package not installed on target device.")
        return 3

    pid_before = get_pid(serial, pkg)

    if args.history_only:
        print("[4/6] History-only mode: skip launch, preserve existing logs")
    else:
        print("[4/6] Preparing capture and launching app")
        if not args.no_clear:
            clear_logcat(serial)
        launch_app(serial, pkg)

    print(f"[5/6] Waiting {args.wait}s")
    time.sleep(max(1, args.wait))

    print("[6/6] Collecting and analyzing logs")
    pid_after = get_pid(serial, pkg)
    log_text = dump_logcat(serial)
    exit_info = get_exit_info(serial, pkg)
    lines = log_text.splitlines()
    verdict, sections = detect_crash_sections(lines, pkg, pid_after or pid_before)

    log_file, summary_file = save_outputs(
        base_dir=args.out,
        pkg=pkg,
        serial=serial,
        log_text=log_text,
        verdict=verdict,
        sections=sections,
        pid_before=pid_before,
        pid_after=pid_after,
    )
    exit_info_file = save_exit_info(args.out, pkg, exit_info)
    suspicious_exit_info = extract_suspicious_exit_info(exit_info)

    print("\n=== Diagnosis Result ===")
    for item in verdict:
        print(f"- {item}")
    if pid_before and pid_after is None:
        print("- App process disappeared after launch, likely crashed or was killed.")

    print(f"\nFull log saved to: {log_file}")
    print(f"Summary saved to:  {summary_file}")
    if exit_info_file:
        print(f"Exit info saved to: {exit_info_file}")

    if suspicious_exit_info:
        print("\nHistorical suspicious exits (latest matched lines):")
        for line in suspicious_exit_info[:5]:
            print(f"- {line}")

    if sections:
        print("\nKey crash snippets (first 2):")
        for idx, section in enumerate(sections[:2], start=1):
            print(f"\n--- snippet {idx} ---")
            print(section)
    else:
        print("\nNo crash snippets extracted. You can increase --wait and retry.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
