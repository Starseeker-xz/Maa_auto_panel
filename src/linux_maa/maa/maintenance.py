from __future__ import annotations

import json
import re
import subprocess
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from linux_maa.maa.runtime import MaaRuntime


MAINTENANCE_COMMANDS = {
    "core-update": ("更新 MaaCore 与基础资源", ["update", "--batch"]),
    "resource-update": ("热更新资源", ["hot-update", "--batch"]),
    "cli-update": ("更新 maa-cli", ["self", "update", "--batch"]),
}

DEFAULT_CORE_API_URL = "https://github.com/MaaAssistantArknights/MaaRelease/raw/main/MaaAssistantArknights/api/version/"
DEFAULT_CLI_API_URL = "https://github.com/MaaAssistantArknights/maa-cli/raw/version/"


@dataclass
class MaintenanceActionState:
    id: str
    kind: str
    title: str
    status: str
    created_at: str
    updated_at: str
    return_code: int | None = None
    output: deque[str] = field(default_factory=lambda: deque(maxlen=1000))
    process: subprocess.Popen[str] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "return_code": self.return_code,
            "output": list(self.output),
        }


class MaintenanceActionManager:
    def __init__(self, runtime: MaaRuntime) -> None:
        self.runtime = runtime
        self._lock = threading.Lock()
        self._current: MaintenanceActionState | None = None

    def current(self) -> MaintenanceActionState | None:
        with self._lock:
            return self._current

    def start(self, kind: str) -> MaintenanceActionState:
        command_info = MAINTENANCE_COMMANDS.get(kind)
        if command_info is None:
            raise ValueError(f"Unsupported maintenance action: {kind}")

        title, args = command_info
        with self._lock:
            if self._current and self._current.status == "running":
                raise RuntimeError(f"Maintenance action already running: {self._current.title}")
            now = datetime.now().isoformat(timespec="seconds")
            state = MaintenanceActionState(
                id=uuid.uuid4().hex[:12],
                kind=kind,
                title=title,
                status="running",
                created_at=now,
                updated_at=now,
            )
            self._current = state

        thread = threading.Thread(target=self._run, args=(state, args), daemon=True)
        thread.start()
        return state

    def inspect_update_info(self, cli_config: dict[str, Any]) -> dict[str, object]:
        errors: list[str] = []
        current = _current_versions(self.runtime, errors)
        latest_core = _latest_core_info(cli_config, current.get("maa_core"), errors)
        latest_cli = _latest_cli_info(cli_config, current.get("maa_cli"), errors)
        hot_resource = _hot_resource_info(self.runtime, cli_config, errors)
        return {
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "current": current,
            "latest": {
                "maa_core": latest_core,
                "maa_cli": latest_cli,
                "hot_resource": hot_resource,
            },
            "errors": errors,
        }

    def _append(self, state: MaintenanceActionState, text: str) -> None:
        with self._lock:
            state.output.append(text)
            state.updated_at = datetime.now().isoformat(timespec="seconds")

    def _set_done(self, state: MaintenanceActionState, status: str, return_code: int | None) -> None:
        with self._lock:
            state.status = status
            state.return_code = return_code
            state.updated_at = datetime.now().isoformat(timespec="seconds")
            state.process = None

    def _run(self, state: MaintenanceActionState, args: list[str]) -> None:
        cmd = [str(self.runtime.maa_bin), *args]
        self._append(state, f"$ {' '.join(cmd)}\n")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.runtime.repo_root,
                env=self.runtime.env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            with self._lock:
                state.process = proc
            assert proc.stdout is not None
            for line in proc.stdout:
                self._append(state, line)
            return_code = proc.wait()
            self._set_done(state, "succeeded" if return_code == 0 else "failed", return_code)
        except Exception as exc:
            self._append(state, f"维护动作失败: {exc}\n")
            self._set_done(state, "failed", None)


def _current_versions(runtime: MaaRuntime, errors: list[str]) -> dict[str, object]:
    versions: dict[str, object] = {}
    try:
        proc = subprocess.run(
            [str(runtime.maa_bin), "version"],
            cwd=runtime.repo_root,
            env=runtime.env(),
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            errors.append(f"读取 maa version 失败: {proc.stderr or proc.stdout}".strip())
        for line in proc.stdout.splitlines():
            if line.lower().startswith("maa-cli"):
                versions["maa_cli"] = _extract_version(line)
            if line.lower().startswith("maacore"):
                versions["maa_core"] = _extract_version(line)
    except Exception as exc:
        errors.append(f"读取 maa 版本失败: {exc}")

    versions["base_resource"] = _resource_version(runtime.data_home / "maa" / "resource" / "version.json")
    versions["hot_resource"] = _resource_version(runtime.data_home / "maa" / "MaaResource" / "resource" / "version.json")
    return versions


def _latest_core_info(cli_config: dict[str, Any], current_version: object, errors: list[str]) -> dict[str, object]:
    core_config = _dict_value(cli_config.get("core"))
    channel = str(core_config.get("channel") or "Stable")
    api_url = str(core_config.get("api_url") or DEFAULT_CORE_API_URL)
    url = _join_api_url(api_url, f"{channel.lower()}.json")
    data = _get_json(url, errors, label="MaaCore 更新信息")
    version = str(data.get("version") or "") if isinstance(data, dict) else ""
    details = _dict_value(data.get("details")) if isinstance(data, dict) else {}
    return {
        "channel": channel,
        "api_url": url,
        "version": version,
        "published_at": details.get("published_at"),
        "html_url": details.get("html_url"),
        "update_available": _is_newer(str(current_version or ""), version),
    }


def _latest_cli_info(cli_config: dict[str, Any], current_version: object, errors: list[str]) -> dict[str, object]:
    cli_section = _dict_value(cli_config.get("cli"))
    channel = str(cli_section.get("channel") or "Stable")
    api_url = str(cli_section.get("api_url") or DEFAULT_CLI_API_URL)
    url = _join_api_url(api_url, f"{channel.lower()}.json")
    data = _get_json(url, errors, label="maa-cli 更新信息")
    version = str(data.get("version") or "") if isinstance(data, dict) else ""
    details = _dict_value(data.get("details")) if isinstance(data, dict) else {}
    return {
        "channel": channel,
        "api_url": url,
        "version": version,
        "tag": details.get("tag"),
        "commit": details.get("commit"),
        "update_available": _is_newer(str(current_version or ""), version),
    }


def _hot_resource_info(runtime: MaaRuntime, cli_config: dict[str, Any], errors: list[str]) -> dict[str, object]:
    resource = _dict_value(cli_config.get("resource"))
    remote = _dict_value(resource.get("remote"))
    branch = str(remote.get("branch") or "main")
    url = str(remote.get("url") or "https://github.com/MaaAssistantArknights/MaaResource.git")
    repo = runtime.data_home / "maa" / "MaaResource"
    local_commit = _git_output(["-C", str(repo), "rev-parse", "HEAD"], errors, label="本地热更资源 commit") if repo.exists() else ""
    remote_commit = _git_output(["ls-remote", url, f"refs/heads/{branch}"], errors, label="远端热更资源 commit")
    if remote_commit:
        remote_commit = remote_commit.split()[0]
    return {
        "branch": branch,
        "url": url,
        "local_commit": local_commit,
        "remote_commit": remote_commit,
        "update_available": bool(local_commit and remote_commit and local_commit != remote_commit),
    }


def _resource_version(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        now = int(datetime.now(timezone.utc).timestamp())
        activity = _dict_value(data.get("activity"))
        gacha = _dict_value(data.get("gacha"))
        activity_time = int(activity.get("time") or 0)
        gacha_time = int(gacha.get("time") or 0)
        if now >= gacha_time > activity_time:
            name = str(gacha.get("pool") or "")
        elif now >= activity_time:
            name = str(activity.get("name") or "")
        elif now >= gacha_time:
            name = str(gacha.get("pool") or "")
        else:
            name = ""
        return {
            "path": str(path),
            "exists": True,
            "name": name,
            "last_updated": data.get("last_updated"),
        }
    except Exception as exc:
        return {"path": str(path), "exists": True, "error": str(exc)}


def _get_json(url: str, errors: list[str], *, label: str) -> dict[str, Any]:
    try:
        response = requests.get(url, timeout=12)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        errors.append(f"{label}获取失败: {exc}")
        return {}


def _git_output(args: list[str], errors: list[str], *, label: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            errors.append(f"{label}获取失败: {proc.stderr.strip() or proc.stdout.strip()}")
            return ""
        return proc.stdout.strip()
    except Exception as exc:
        errors.append(f"{label}获取失败: {exc}")
        return ""


def _extract_version(line: str) -> str:
    parts = line.strip().split()
    return parts[-1].removeprefix("v") if parts else ""


def _join_api_url(base_url: str, filename: str) -> str:
    return f"{base_url.rstrip('/')}/{filename}"


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_newer(current: str, latest: str) -> bool:
    if not current or not latest:
        return False
    current = current.removeprefix("v")
    latest = latest.removeprefix("v")
    if current == latest:
        return False
    return _version_key(current) < _version_key(latest)


def _version_key(value: str) -> tuple[tuple[int, ...], str]:
    numeric = tuple(int(part) for part in re.findall(r"\d+", value)[:4])
    return numeric, value
