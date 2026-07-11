from __future__ import annotations

import re
import subprocess


class ADBDevice:
    """Android device managed via ADB, identified by serial number."""
    def __init__(self, serial: str, adb_path: str = "adb") -> None:
        """Initialize with device serial and optional ADB binary path."""
        self.serial = serial
        self.adb_path = adb_path

    def run(self, args: list[str], *, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        cmd = [self.adb_path, "-s", self.serial] + args
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

    def connect(self) -> None:
        """Connect via ADB if serial is a network address, else no-op."""
        if ":" in self.serial:
            subprocess.run([self.adb_path, "connect", self.serial], capture_output=True, text=True, check=False)

    def is_connected(self) -> bool:
        """Return True if device shows as connected in adb devices output."""
        try:
            result = subprocess.run(
                [self.adb_path, "devices"],
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            return False

        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == self.serial and parts[1] == "device":
                return True
        return False

    def get_installed_version_code(self, package_name: str) -> int:
        """Return versionCode of installed package via dumpsys, or -1 if not found."""
        proc = self.run(["shell", "dumpsys", "package", package_name], check=False)
        if proc.returncode != 0:
            return -1
        match = re.search(r"versionCode=(\d+)", proc.stdout)
        return int(match.group(1)) if match else -1

    def install_apk(self, apk_path: str) -> None:
        """Install or replace an APK with 600s timeout; return True on success."""
        self.run(["install", "-r", apk_path], timeout=600)

    def get_apk_path(self, package_name: str) -> str:
        """Query installed filesystem path of a package on the device."""
        proc = self.run(["shell", "pm", "path", package_name], check=False)
        output = proc.stdout.strip()
        if output.startswith("package:"):
            return output.split("package:", 1)[1].strip()
        return ""

    def pull_file(self, remote_path: str, local_path: str) -> bool:
        """Pull a file from device to local path; return True on success."""
        proc = self.run(["pull", remote_path, local_path], check=False, timeout=600)
        return proc.returncode == 0

