from __future__ import annotations

from copy import deepcopy
from typing import Any

TASK_SUFFIXES = (".toml", ".json", ".yaml", ".yml")
WRITABLE_TASK_SUFFIXES = (".toml", ".json")
MANAGED_PARAMS_KEY = "managed_params"
RUNTIME_PLACEHOLDER_PREFIX = "__framework_runtime__:"
MANAGED_ARRAY_PLACEHOLDER_PREFIX = f"{RUNTIME_PLACEHOLDER_PREFIX}array:"
FIGHT_STAGE_PLACEHOLDER = f"{RUNTIME_PLACEHOLDER_PREFIX}fight_stage"
INFRAST_PLAN_INDEX_PLACEHOLDER = f"{RUNTIME_PLACEHOLDER_PREFIX}infrast_plan_index"


def strip_framework_task_metadata(data: dict[str, object]) -> dict[str, object]:
    """Return task config copy with all framework metadata removed."""
    sanitized = dict(data)
    tasks = sanitized.get("tasks")
    if not isinstance(tasks, list):
        return sanitized

    clean_tasks: list[object] = []
    for task in tasks:
        if isinstance(task, dict):
            clean_tasks.append({key: value for key, value in task.items() if key != "framework"})
        else:
            clean_tasks.append(task)
    sanitized["tasks"] = clean_tasks
    return sanitized


def prepare_framework_task_config(data: dict[str, object], runtime: object, messages: list[str] | None = None) -> dict[str, object]:
    """Project framework metadata into a config that raw maa-cli can run."""

    prepared = deepcopy(data)
    tasks = prepared.get("tasks")
    if not isinstance(tasks, list):
        return strip_framework_task_metadata(prepared)

    root_client = str(prepared.get("client_type") or "Official")
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            continue
        raw_metadata = task.get("framework")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        params = deepcopy(task.get("params")) if isinstance(task.get("params"), dict) else {}
        task_type = str(task.get("type") or "")
        skip_reason = _apply_managed_params_for_runtime(
            params,
            metadata,
            task_type=task_type,
            runtime=runtime,
            root_client=root_client,
            messages=messages,
        )
        if skip_reason:
            params["enable"] = False
            _append_message(messages, f"跳过子任务 {index} ({task.get('name') or task.get('type') or '未命名'}): {skip_reason}")
        task["params"] = params

    return strip_framework_task_metadata(prepared)


def task_items_to_config_data(base_data: dict[str, Any], task_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge base config data with task items list into full maa-cli task config dict."""
    data = {key: deepcopy(value) for key, value in base_data.items() if key != "tasks"}
    data["tasks"] = [task_item_to_config_task(item) for item in task_items]
    return data


def task_item_to_config_task(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a frontend task item dict back to a native maa-cli task dict."""
    task: dict[str, Any] = {
        "name": str(item.get("name") or item.get("type") or "Task"),
        "type": str(item.get("type") or "Unknown"),
    }

    strategy = item.get("strategy")
    if strategy is not None:
        task["strategy"] = deepcopy(strategy)

    params = deepcopy(item.get("params")) if isinstance(item.get("params"), dict) else {}
    metadata = deepcopy(item.get("framework")) if isinstance(item.get("framework"), dict) else {}
    params, metadata = project_managed_params_for_config(str(item.get("type") or "Unknown"), params, metadata)

    enabled = item.get("enabled")
    if isinstance(enabled, bool) and (not enabled or "enable" in params):
        params["enable"] = enabled
    if params:
        task["params"] = params

    variants = deepcopy(item.get("variants")) if isinstance(item.get("variants"), list) else []
    if variants:
        task["variants"] = variants

    item_id = item.get("id")
    if isinstance(item_id, str) and item_id.strip():
        metadata["id"] = item_id.strip()
    if metadata:
        task["framework"] = metadata

    return task


def ensure_managed_metadata(task_type: str, params: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    """Ensure managed_params exist in metadata, auto-filling defaults for known task types."""
    next_metadata = deepcopy(metadata)
    managed = _managed_params(next_metadata)

    for key, value in params.items():
        if isinstance(value, list) and key not in managed:
            managed[key] = {
                "type": "array",
                "items": [{"value": deepcopy(item), "enabled": True} for item in value],
            }

    if task_type == "Fight" and "stage" not in managed:
        current = params.get("stage", "")
        values = [] if _is_runtime_placeholder(current) else [_normalize_fight_stage_value(current)]
        managed["stage"] = {
            "type": "runtime",
            "handler": "fight_stage",
            "items": [{"value": deepcopy(item), "enabled": True} for item in values],
        }
    elif task_type == "Fight":
        _normalize_fight_stage_spec(managed.get("stage"))

    if task_type == "Infrast" and "plan_index" not in managed:
        current = params.get("plan_index", 0)
        managed["plan_index"] = {
            "type": "runtime",
            "handler": "infrast_plan_index",
            "value": INFRAST_PLAN_INDEX_PLACEHOLDER if _is_runtime_placeholder(current) else str(current),
        }

    if managed:
        next_metadata[MANAGED_PARAMS_KEY] = managed
    return next_metadata


def inflate_managed_params_for_edit(task_type: str, params: dict[str, Any], metadata: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Expand managed param placeholders to actual values for display in edit UI."""
    next_metadata = ensure_managed_metadata(task_type, params, metadata)
    next_params = deepcopy(params)
    for key, spec in _managed_params(next_metadata).items():
        if not isinstance(spec, dict):
            continue
        spec_type = spec.get("type")
        handler = spec.get("handler")
        if spec_type == "array":
            next_params[key] = [deepcopy(item.get("value")) for item in _managed_items(spec)]
        elif spec_type == "runtime" and handler == "fight_stage":
            next_params[key] = [_normalize_fight_stage_value(item.get("value")) for item in _managed_items(spec)]
        elif spec_type == "runtime" and handler == "infrast_plan_index":
            value = spec.get("value", INFRAST_PLAN_INDEX_PLACEHOLDER)
            next_params[key] = INFRAST_PLAN_INDEX_PLACEHOLDER if _is_auto_infrast_plan_value(value) else str(value)
    return next_params, next_metadata


def project_managed_params_for_config(task_type: str, params: dict[str, Any], metadata: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    next_metadata = ensure_managed_metadata(task_type, params, metadata)
    next_params = deepcopy(params)
    for key, spec in _managed_params(next_metadata).items():
        if not isinstance(spec, dict):
            continue
        spec_type = spec.get("type")
        handler = spec.get("handler")
        if spec_type == "array":
            next_params[key] = managed_array_placeholder(key)
        elif spec_type == "runtime" and handler == "fight_stage":
            next_params[key] = FIGHT_STAGE_PLACEHOLDER
        elif spec_type == "runtime" and handler == "infrast_plan_index":
            next_params[key] = INFRAST_PLAN_INDEX_PLACEHOLDER
    return next_params, next_metadata


def _apply_managed_params_for_runtime(
    params: dict[str, Any],
    metadata: dict[str, Any],
    *,
    task_type: str,
    runtime: object,
    root_client: str,
    messages: list[str] | None,
) -> str | None:
    runtime_metadata = ensure_managed_metadata(task_type, params, metadata)
    managed = _managed_params(runtime_metadata)
    handled: set[str] = set()
    for key, spec in managed.items():
        if not isinstance(spec, dict):
            continue
        spec_type = spec.get("type")
        handler = str(spec.get("handler") or "")
        if spec_type == "array":
            params[key] = resolve_managed_array(runtime_metadata, key)
            handled.add(key)
            continue
        if spec_type != "runtime":
            continue
        try:
            if handler == "fight_stage":
                selected = _resolve_fight_stage(runtime, spec, params, root_client)
                if selected is None:
                    return f"{key} 没有当前可用关卡"
                params[key] = selected
                _append_message(messages, f"选择战斗关卡: {_describe_fight_stage(selected)}")
                handled.add(key)
            elif handler == "infrast_plan_index":
                selected_plan_index = _resolve_infrast_plan_index(runtime, spec, params)
                params[key] = selected_plan_index
                _append_message(messages, f"选择基建计划: {_describe_infrast_plan(runtime, params, selected_plan_index)}")
                handled.add(key)
            else:
                return f"{key} 使用了未知运行时占位处理器 {handler!r}"
        except Exception as exc:
            return f"{key} 运行时占位解析失败: {exc}"

    for key, value in list(params.items()):
        if key in handled or not _is_runtime_placeholder(value):
            continue
        handler = str(value).removeprefix(RUNTIME_PLACEHOLDER_PREFIX)
        return f"{key} 使用了没有 metadata 配置的运行时占位处理器 {handler!r}"

    return None


def managed_array_placeholder(key: str) -> str:
    """Return the standard managed array placeholder string for a given key."""
    return f"{MANAGED_ARRAY_PLACEHOLDER_PREFIX}{key}"


def resolve_managed_array(metadata: dict[str, Any], key: str) -> list[Any]:
    """Resolve a managed array from metadata, returning only enabled items."""
    spec = _managed_params(metadata).get(key)
    if not isinstance(spec, dict) or spec.get("type") != "array":
        raise ValueError(f"metadata.{MANAGED_PARAMS_KEY}.{key} is not a managed array")
    return [deepcopy(item.get("value")) for item in _managed_items(spec) if item.get("enabled") is not False]


def _resolve_fight_stage(runtime: object, spec: dict[str, Any], params: dict[str, Any], root_client: str) -> str | None:
    from maa_auto_panel.maa.stages import MaaStageService

    client = str(params.get("client_type") or root_client or "Official")
    stage_plan = [_normalize_fight_stage_value(item.get("value")) for item in _managed_items(spec) if item.get("enabled") is not False]
    return MaaStageService(runtime).resolve_first_open_stage(stage_plan, client=client)


def _resolve_infrast_plan_index(runtime: object, spec: dict[str, Any], params: dict[str, Any]) -> int:
    from maa_auto_panel.maa.infrast import MaaInfrastService

    filename = str(params.get("filename") or "")
    return MaaInfrastService(runtime).resolve_plan_index(filename=filename, value=spec.get("value"))


def _managed_params(metadata: dict[str, Any]) -> dict[str, Any]:
    managed = metadata.get(MANAGED_PARAMS_KEY)
    if isinstance(managed, dict):
        return managed
    managed = {}
    metadata[MANAGED_PARAMS_KEY] = managed
    return managed


def _managed_items(spec: dict[str, Any]) -> list[dict[str, Any]]:
    items = spec.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _normalize_fight_stage_spec(spec: object) -> None:
    if not isinstance(spec, dict):
        return
    for item in _managed_items(spec):
        item["value"] = _normalize_fight_stage_value(item.get("value"))


def _normalize_fight_stage_value(value: object) -> str:
    from maa_auto_panel.maa.stages import normalize_stage_plan_value

    return normalize_stage_plan_value(value)


def _describe_fight_stage(value: object) -> str:
    text = str(value)
    return "当前/上次" if text == "" else text


def _describe_infrast_plan(runtime: object, params: dict[str, Any], plan_index: int) -> str:
    from maa_auto_panel.maa.infrast import MaaInfrastService

    filename = str(params.get("filename") or "").strip()
    try:
        return MaaInfrastService(runtime).describe_plan(filename=filename, plan_index=plan_index)
    except Exception:
        pass
    if filename:
        return f"{filename} / 计划 #{plan_index}"
    return f"计划 #{plan_index}"


def _is_runtime_placeholder(value: object) -> bool:
    return isinstance(value, str) and value.startswith(RUNTIME_PLACEHOLDER_PREFIX)


def _is_auto_infrast_plan_value(value: object) -> bool:
    return value in {None, "", -1, "__auto__", INFRAST_PLAN_INDEX_PLACEHOLDER}


def _safe_int(value: object, *, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _append_message(messages: list[str] | None, message: str) -> None:
    if messages is not None:
        messages.append(message)
