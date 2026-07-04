from __future__ import annotations

import json
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from linux_maa.diagnostics import Diagnostics, get_logger
from linux_maa.logs import RunLogBuffer
from linux_maa.maa.log_templates import register_maa_log_sources
from linux_maa.maa.runtime import MaaRuntime
from linux_maa.process import run_streaming_process
from linux_maa.run_state import RunStateStore
from linux_maa.utils import dict_value, extract_version, is_newer_version


logger = get_logger(__name__)


MAINTENANCE_COMMANDS = {
    "core-update": ("更新 MaaCore 与基础资源", ["update", "--batch"]),
    "resource-update": ("热更新资源", ["hot-update", "--batch"]),
    "cli-update": ("更新 maa-cli", ["self", "update", "--batch"]),
}

DEFAULT_CORE_API_URL = "https://github.com/MaaAssistantArknights/MaaRelease/raw/main/MaaAssistantArknights/api/version/"
DEFAULT_CLI_API_URL = "https://github.com/MaaAssistantArknights/maa-cli/raw/version/"


@dataclass
class MaintenanceActionState:
    """Lifecycle state of a maintenance action with logs and process handle."""
    id: str
    kind: str
    title: str
    status: str
    created_at: str
    updated_at: str
    return_code: int | None = None
    log_file: str | None = None
    log_files: dict[str, str] = field(default_factory=dict)
    log: RunLogBuffer = field(default_factory=lambda: RunLogBuffer(max_output_chunks=1000))
    process: subprocess.Popen[str] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "return_code": self.return_code,
            "log_file": self.log_file,
            "log_files": dict(self.log_files),
        }
        data.update(self.log.to_dict())
        return data


class MaintenanceActionManager:
    """Manages maintenance actions: core/resource/cli updates with version checks."""
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
            state.log_file = self.diagnostics.maa_cli_log_file(state.id)
            state.log_files = self.diagnostics.maa_cli_log_files(state.id)
            _register_maa_cli_log_sources(state.log)
            self.run_state.create_maintenance_run(
                run_id=state.id,
                kind=kind,
                title=title,
                log_file=state.log_file,
                log_files=state.log_files,
                event_log_file=self.diagnostics.event_log_file(state.id),
            )
            self._current = state
            logger.info("maintenance action started run_id=%s kind=%s title=%s", state.id, kind, title)

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

    def _append(self, state: MaintenanceActionState, text: str, source: str = "framework") -> None:
        if source.startswith("maa-cli:"):
            self.diagnostics.append_maa_cli_output(state.id, source.split(":", 1)[1], text)
            appended = state.log.append(text, source=source)
        else:
            self.diagnostics.append_run_event(state.id, "maintenance", source, text)
            logger.info("maintenance event run_id=%s source=%s text=%s", state.id, source, text.strip())
            appended = state.log.append(
                f"{text.strip()}\n",
                source="framework:event",
                metadata={"time": datetime.now().strftime("%H:%M:%S"), "tone": "info"},
            )
        with self._lock:
            if appended:
                state.updated_at = datetime.now().isoformat(timespec="seconds")

    def _set_done(self, state: MaintenanceActionState, status: str, return_code: int | None) -> None:
        with self._lock:
            state.status = status
            state.return_code = return_code
            state.updated_at = datetime.now().isoformat(timespec="seconds")
            state.process = None
        self.run_state.add_single_attempt(
            run_id=state.id,
            status=status,
            started_at=state.created_at,
            ended_at=state.updated_at,
            return_code=return_code,
            task_results=state.log.task_results(),
            log_entries=state.log.entries(),
            log_file=state.log_file,
            log_files=state.log_files,
        )
        self.run_state.finish_generic_run(state.id, status=status, return_code=return_code)
        self.run_state.enforce_retention()
        self.diagnostics.enforce_retention()
        logger.info("maintenance action finished run_id=%s status=%s return_code=%s", state.id, status, return_code)

    def _run(self, state: MaintenanceActionState, args: list[str]) -> None:
        cmd = [str(self.runtime.maa_bin), *args]
        self._append(state, f"$ {' '.join(cmd)}\n")
        try:
            result = run_streaming_process(
                self.runtime,
                cmd,
                env=self.runtime.env(),
                on_output=lambda text: None,
                on_stream_output=lambda stream, text: self._append(state, text, f"maa-cli:{stream}"),
                on_process=lambda proc: self._set_process(state, proc),
            )
            if state.log.flush():
                with self._lock:
                    state.updated_at = datetime.now().isoformat(timespec="seconds")
            return_code = result.return_code
            self._set_done(state, "succeeded" if return_code == 0 else "failed", return_code)
        except Exception as exc:
            self._append(state, f"维护动作失败: {exc}\n")
            logger.exception("maintenance action failed run_id=%s", state.id)
            self._set_done(state, "failed", None)

    def _set_process(self, state: MaintenanceActionState, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            state.process = proc


def _register_maa_cli_log_sources(log: RunLogBuffer) -> None:
    register_maa_log_sources(log)


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
                versions["maa_cli"] = extract_version(line)
            if line.lower().startswith("maacore"):
                versions["maa_core"] = extract_version(line)
    except Exception as exc:
        errors.append(f"读取 maa 版本失败: {exc}")

    versions["base_resource"] = _resource_version(runtime.data_home / "maa" / "resource" / "version.json")
    versions["hot_resource"] = _resource_version(runtime.data_home / "maa" / "MaaResource" / "resource" / "version.json")
    return versions


def _latest_core_info(cli_config: dict[str, Any], current_version: object, errors: list[str]) -> dict[str, object]:
    core_config = dict_value(cli_config.get("core"))
    channel = str(core_config.get("channel") or "Stable")
    api_url = str(core_config.get("api_url") or DEFAULT_CORE_API_URL)
    url = _join_api_url(api_url, f"{channel.lower()}.json")
    data = _get_json(url, errors, label="MaaCore 更新信息")
    version = str(data.get("version") or "") if isinstance(data, dict) else ""
    details = dict_value(data.get("details")) if isinstance(data, dict) else {}
    return {
        "channel": channel,
        "api_url": url,
        "version": version,
        "published_at": details.get("published_at"),
        "html_url": details.get("html_url"),
        "update_available": is_newer_version(str(current_version or ""), version),
    }


def _latest_cli_info(cli_config: dict[str, Any], current_version: object, errors: list[str]) -> dict[str, object]:
    cli_section = dict_value(cli_config.get("cli"))
    channel = str(cli_section.get("channel") or "Stable")
    api_url = str(cli_section.get("api_url") or DEFAULT_CLI_API_URL)
    url = _join_api_url(api_url, f"{channel.lower()}.json")
    data = _get_json(url, errors, label="maa-cli 更新信息")
    version = str(data.get("version") or "") if isinstance(data, dict) else ""
    details = dict_value(data.get("details")) if isinstance(data, dict) else {}
    return {
        "channel": channel,
        "api_url": url,
        "version": version,
        "tag": details.get("tag"),
        "commit": details.get("commit"),
        "update_available": is_newer_version(str(current_version or ""), version),
    }


def _hot_resource_info(runtime: MaaRuntime, cli_config: dict[str, Any], errors: list[str]) -> dict[str, object]:
    resource = dict_value(cli_config.get("resource"))
    remote = dict_value(resource.get("remote"))
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
        activity = dict_value(data.get("activity"))
        gacha = dict_value(data.get("gacha"))
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


def _join_api_url(base_url: str, filename: str) -> str:
    return f"{base_url.rstrip('/')}/{filename}"
