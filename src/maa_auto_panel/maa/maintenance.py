from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from maa_auto_panel.config.app_settings import FrameworkSettingsManager
from maa_auto_panel.diagnostics import Diagnostics, get_logger
from maa_auto_panel.errors import InvalidRequest
from maa_auto_panel.maa.log_templates import configure_maa_log_template, maa_log_source_specs
from maa_auto_panel.maa.runtime import MaaRuntime
from maa_auto_panel.run_manager.command import CommandSpec
from maa_auto_panel.run_manager.contracts import RunStartPlan, RunTextTemplates
from maa_auto_panel.run_manager.coordinator import RunCoordinator
from maa_auto_panel.run_manager.logs import RunLogProfile
from maa_auto_panel.run_manager.manager import GenericRunManager
from maa_auto_panel.run_manager.state import LiveRun
from maa_auto_panel.run_manager.store import RunStateStore
from maa_auto_panel.run_resources import maa_runtime_resource
from maa_auto_panel.utils import dict_value, extract_version, is_newer_version


logger = get_logger(__name__)


MAINTENANCE_COMMANDS = {
    "core-update": ("更新 MaaCore 与基础资源", ["update", "--batch"]),
    "resource-update": ("热更新资源", ["hot-update", "--batch"]),
    "cli-update": ("更新 maa-cli", ["self", "update", "--batch"]),
}

DEFAULT_CORE_API_URL = "https://github.com/MaaAssistantArknights/MaaRelease/raw/main/MaaAssistantArknights/api/version/"
DEFAULT_CLI_API_URL = "https://github.com/MaaAssistantArknights/maa-cli/raw/version/"


class MaintenanceActionManager:
    """Manages maintenance actions: core/resource/cli updates with version checks."""

    def __init__(
        self,
        runtime: MaaRuntime,
        run_state: RunStateStore,
        diagnostics: Diagnostics,
        framework_settings: FrameworkSettingsManager,
        run_coordinator: RunCoordinator,
    ) -> None:
        self.runtime = runtime
        self.diagnostics = diagnostics
        self.framework_settings = framework_settings
        self.runs = GenericRunManager(
            run_state,
            self.diagnostics,
            run_coordinator,
            resource_wait_timeout_seconds=self.framework_settings.resource_wait_timeout_seconds,
        )

    def current(self) -> LiveRun | None:
        return self.runs.current()

    def current_response(self, *, include_logs: bool = True) -> dict[str, object]:
        return self.runs.current_response(include_logs=include_logs)

    def wait_for_change(self, last_version: int, timeout: float | None = None) -> int:
        return self.runs.wait_for_change(last_version, timeout)

    def start(self, kind: str) -> LiveRun:
        command_info = MAINTENANCE_COMMANDS.get(kind)
        if command_info is None:
            raise InvalidRequest(f"Unsupported maintenance action: {kind}")

        title, args = command_info
        run_id = uuid.uuid4().hex[:12]
        cmd = [str(self.runtime.maa_bin), *args]
        log_profile = _maa_cli_log_profile(self.diagnostics)
        state = self.runs.start(
            RunStartPlan(
                kind="maintenance",
                title=title,
                command=CommandSpec(cmd, cwd=self.runtime.repo_root, env=self.runtime.env()),
                max_retries=1,
                timeouts=self.framework_settings.run_timeouts(),
                log_profile=log_profile,
                log_files=self.diagnostics.stream_log_files("maa-cli", run_id),
                event_log_file=self.diagnostics.event_log_file(run_id),
                metadata={"maintenance_kind": kind},
                history_scope=("maintenance", kind),
                resources=(maa_runtime_resource(exclusive=True),),
                priority_name="normal",
                preemptible=False,
                text=RunTextTemplates(
                    process_name="维护动作",
                    start=f"$ {' '.join(cmd)}",
                    completed="维护动作完成",
                    exit_code="维护动作退出码: {return_code}",
                    retry_next="准备重试维护动作。",
                    start_failed="维护动作失败: {error}",
                    stop_requested="收到停止请求，正在终止维护动作...",
                    force_stop_requested="收到强制停止请求，正在强杀维护动作...",
                    execution_failed="维护动作失败: {error}",
                ),
            ),
            run_id=run_id,
        )
        logger.info("maintenance action started run_id=%s kind=%s title=%s", state.id, kind, title)
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

def _maa_cli_log_profile(diagnostics: Diagnostics) -> RunLogProfile:
    return RunLogProfile(
        source_specs=maa_log_source_specs(),
        configure_buffer=configure_maa_log_template,
        source_for_stream=lambda stream: f"maa-cli:{stream}",
        diagnostic_sink=diagnostics.stream_sink("maa-cli"),
    )


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
