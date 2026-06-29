# Session 2026-06-26_1727-webui-config-runner

## Task

Build a minimal WebUI to select managed config files, run maa-cli, and display current output. Normalize config management and organize src structure.

## Work Completed

- Created the session id `2026-06-26_1727-webui-config-runner`.
- Read global/project state before editing.
- Added `linux-maa webui` command backed by FastAPI/Uvicorn.
- Implemented managed config listing/reading through `src/linux_maa/config/manager.py`.
- Implemented WebUI/API in `src/linux_maa/web/app.py`.
- Reorganized source into domain packages:
  - `src/linux_maa/android/`
  - `src/linux_maa/game/`
  - `src/linux_maa/maa/`
  - `src/linux_maa/config/`
  - `src/linux_maa/web/`
- Left thin compatibility modules for old imports: `adb.py`, `constants.py`, `game_update.py`, `maa_runner.py`.
- Added FastAPI/Uvicorn/Pydantic dependencies and ran `uv sync`.

## Tests and Outcomes

- `uv run python -m compileall src`: passed.
- `uv run linux-maa --help`: passed and shows `webui`.
- `uv run linux-maa run-maa-task --help`: passed and shows `--profile`.
- `scripts/maa-env maa run startup-smoke --batch --profile default --dry-run`: passed.
- `GET http://127.0.0.1:8000/`: returned `200`.
- `GET http://127.0.0.1:8000/api/configs`: returned profile `default` and tasks `award-no-mail`, `startup-smoke`, `test`.
- `POST /api/runs` with `startup-smoke`, 30 second timeout: started and timeout termination worked. It touched Android/game runtime.

## Active Environment Effects

- WebUI is currently running from `uv run linux-maa webui --host 0.0.0.0 --port 8000`.
- Current Uvicorn server process shown by tool output: `25012`.
- LAN URL for user access from `192.168.5.21`: `http://192.168.5.15:8000/`.

## Decisions

- Keep one top-level Python package under `src/` (`linux_maa`) because this is the normal Python src-layout/distribution pattern. Use subpackages inside it for real architecture boundaries.
- Do not stream `runtime/maa/state/maa/debug/asst.log` in the WebUI. It is too low-level for normal operator output.
- The first WebUI slice shows readable maa-cli stdout/stderr/status only. Later progress should be a purpose-built high-level event model, not raw MaaCore logs.

## Mistakes / Lessons

- Tried `python -m json.tool`; this machine does not have a bare `python` executable. Recorded global lesson to use `python3` or `uv run python`.
- Tried FastAPI `TestClient`; current Starlette requires `httpx2`. Recorded project lesson to use uvicorn+curl unless adding that dependency intentionally.

- User clarified `preserve_tags` in `runtime/maa/config/tasks/test.toml` is intentional and should not be rewritten to documented `first_tags`; treat it as a deliberate newer/custom MaaCore parameter under test.

## Direct MaaCore Experiment

- Created scratch script `.codex/conversations/2026-06-26_1727-webui-config-runner/scratch/maacore_direct_run.py`.
- Script uses `ctypes` against `runtime/maa/data/maa/lib/libMaaCore.so`, reads `runtime/maa/config/profiles/default.toml` and `runtime/maa/config/tasks/test.toml`, calls `AsstSetUserDir`, `AsstSetStaticOption`, `AsstLoadResource`, `AsstCreateEx`, `AsstSetInstanceOption`, `AsstConnect`, `AsstAppendTask`, `AsstStart`, polls `AsstRunning`, and stops on timeout.
- Important finding: `AsstLoadResource` expects the parent directory that contains `resource/`, not the resource directory itself. Passing `runtime/maa/data/maa/resource` failed because MaaCore looked for `.../resource/resource`; passing `runtime/maa/data/maa` worked. Hot update resources are loaded by an additional `AsstLoadResource(runtime/maa/data/maa/MaaResource)`.
- Copied `TEMP/排班.json` to `runtime/maa/config/infrast/排班.json`, because maa-cli docs say Infrast relative filenames are under `$MAA_CONFIG_DIR/infrast`; the direct MaaCore script resolves this to an absolute path before appending the task.
- Updated `runtime/maa/config/tasks/test.toml` Infrast params to valid TOML: facility array, reception booleans, `filename = "排班.json"`, `plan_index = 3`. `preserve_tags` was restored and is intentional.
- `scripts/maa-env maa run test --batch --profile default --dry-run` passed after the config edits.
- Direct MaaCore one-task run with `--limit-tasks 1 --max-seconds 45` succeeded through connection, `AsstAppendTask(StartUp)`, `TaskChainStart`, multiple `SubTaskStart/SubTaskCompleted`, then timed out and returned `TaskChainStopped`.
- Direct full `test.toml` run with `--max-seconds 180 --event-level chain` appended all six tasks. Observed task chain progress:
  - `StartUp` started and completed.
  - `Award` started and completed.
  - `Mall` started, emitted `SubTaskError` from `asst::CreditShoppingTask`, then completed.
  - `Infrast` started, emitted `SubTaskError` from `asst::ProcessTask` with internal `first` values including `InfrastOperListTabMoodDoubleClickWhenUnclicked` and later `BattleQuickFormationExpandRole`, then was stopped by the 180 second timeout.
  - `Fight` and `Recruit` did not start during the 180 second run.
- Confirmed: MaaCore returns structured callback events suitable for user-facing progress after filtering. Useful mappings include `TaskChainStart` -> "正在执行 <taskchain>", `TaskChainCompleted` -> "<taskchain> 完成", `TaskChainError`/`SubTaskError` -> "<taskchain> 内部步骤失败/重试/异常", `TaskChainStopped` -> "<taskchain> 已停止", `AllTasksCompleted` -> "全部完成", and `ConnectionInfo` -> connection/screenshot health metadata.

## WebUI maa-cli Verbose Log Output

- User asked to connect WebUI "输出" to maa-cli logs before implementing direct MaaCore callback integration.
- Updated `src/linux_maa/maa/runner.py` WebUI process path to run `maa run <task> --batch --profile <profile> --log-file=<runtime/maa/run-logs/...> -v` and tail that log file while also reading stdout/stderr.
- Important CLI detail: `maa run --log-file` must be passed as `--log-file=<path>`; the split form `--log-file <path>` fails with "unexpected argument".
- Verified with Web API `startup-smoke`, 30s timeout. Output now includes:
  - `Updating hot update files...`
  - `Hot update completed successfully`
  - `Connected`
  - `FastestWayToScreencap RawWithGzip ...`
  - `StartUp Start`
  - `StartUp Completed`
  - `AllTasksCompleted`
  - final Summary
- Active WebUI restarted and running on `0.0.0.0:8000`, process `18365`.
- Added WebUI "输出粒度" selector:
  - `摘要` => no `--log-file`, no `-v`; stdout summary only.
  - `常规` => `--log-file=<path> -v`.
  - `详细` => `--log-file=<path> -v -v`.
  - `追踪` => `--log-file=<path> -v -v -v`.
- API payload field is `log_level` with accepted values `0..3`; `MaaRunRequest` and `MaaRunState` now carry this field.
- Verified `log_level=0` with `startup-smoke`: run succeeded, `log_file` was `None`, and output showed only command, summary, and exit code.
- Active WebUI was restarted again after the selector change and is running on `0.0.0.0:8000`, process `27260`.

## GPU OCR Notes

- `docs/maa-cli/schemas/asst.schema.json` and `docs/maa-cli/config_examples/profiles/default.toml` expose `[static_options] gpu_ocr = <integer>` and `cpu_ocr = false`.
- Current `runtime/maa/config/profiles/default.toml` uses `cpu_ocr = true` and no `gpu_ocr`.
- Upstream user docs describe Windows GUI GPU acceleration as DirectML-based. On this Linux CT, DirectML is not the relevant path.
- CT hardware/devices observed: `/dev/dri/renderD128`, `/dev/dri/card1`, `/dev/nvidia0`, `/dev/nvidiactl`, and `lspci` sees Intel Alder Lake-P iGPU plus NVIDIA RTX 2080 Ti.
- `strings runtime/maa/data/maa/lib/libonnxruntime.so.1` contains provider names including CPU, CUDA, Dml, OpenVINO, ROCM, TensorRT, and CoreML, but this does not prove a provider is usable in this container. Need a deliberate profile test before enabling GPU by default.
