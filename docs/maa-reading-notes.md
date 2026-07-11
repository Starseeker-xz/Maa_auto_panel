# MAA / maa-cli Reading Notes

Source session: `2026-06-26_1620-maa-cli-framework-docs`

## Scope Read

- Mirrored MAA Chinese docs from `MaaAssistantArknights/MaaAssistantArknights` branch `archive/dev-v1`, path `docs/zh-cn`, into `docs/maa-upstream/zh-cn/`.
- Copied selected `maa-cli` schemas and example configs into `docs/maa-cli/`.
- Read first-pass focus areas: CLI install/usage/config, MaaCore integration protocol, callback schema, task-flow schema, connection docs, Windows GUI/newbie/feature docs, Linux/redroid support docs.
- Canonical online references: [install](https://docs.maa.plus/zh-cn/manual/cli/install.html), [usage](https://docs.maa.plus/zh-cn/manual/cli/usage.html), [config](https://docs.maa.plus/zh-cn/manual/cli/config.html), and [integration protocol](https://docs.maa.plus/zh-cn/protocol/integration.html). Prefer the online versions when behavior may have changed since the mirrored snapshot.

## What MAA Is Doing

MAA automates Arknights by connecting to an Android runtime through ADB-like control, taking screenshots, recognizing UI state through template/OCR/feature matching, and executing task chains. The Windows GUI exposes common workflows as configurable task lists, but the underlying MaaCore model is task-chain based and much richer than the GUI.

The GUI task concepts map to MaaCore task types such as:

- `StartUp`: start/wake game and optionally switch account.
- `CloseDown`: close game.
- `Fight`: sanity farming, stage navigation, medicine/stone limits, drops, series mode, some crash recovery.
- `Recruit`: public recruitment.
- `Infrast`: base shift scheduling, including custom base plans.
- `Mall`: credit shop and friend visit.
- `Award`: daily/weekly/mail/event rewards.
- `Roguelike`, `Copilot`, `SSSCopilot`, `Reclamation`, `Depot`, `OperBox`, `Custom`, `SingleStep`, `VideoRecognition`.

## maa-cli Runtime Model

`maa-cli` is a command-line wrapper around MaaCore. It can install/update MaaCore and resources, initialize config, run predefined tasks, and run custom task files.

Important commands:

- `maa install`: install MaaCore and base resources.
- `maa update`: update MaaCore and resources.
- `maa init`: interactively initialize profile/config.
- `maa run <task>`: run a custom task file from `$MAA_CONFIG_DIR/tasks`.
- `maa startup`, `maa fight`, `maa closedown`, etc.: predefined one-off tasks.
- `maa dir config`, `maa dir log`, `maa version`, `maa activity`, `maa cleanup`, `maa import`.

Logs:

- Default log level is `Warn`.
- `MAA_LOG=debug` or `-v` can increase verbosity.
- `--log-file` writes logs to `$(maa dir log)/YYYY/MM/DD/HH:MM:SS.log`, or to an explicit path.
- This is the likely minimum viable observation channel for an external wrapper around maa-cli.

## maa-cli Config Model

The config directory is found with `maa dir config` or overridden with `MAA_CONFIG_DIR`.

Custom tasks live under `$MAA_CONFIG_DIR/tasks`. A task file contains ordered `[[tasks]]` entries:

```toml
[[tasks]]
name = "启动游戏"
type = "StartUp"
params = { client_type = "Bilibili", start_game_enabled = true }
```

Task variants allow built-in conditional parameter selection. Supported conditions include:

- `Time`
- `DateTime`
- `Weekday`
- `DayMod`
- `OnSideStory`
- logical `And`, `Or`, `Not`

Variant strategy:

- Default is `first`: first matching variant wins.
- `merge`: matching variants are merged in order, later values override earlier values.

Important limitation: maa-cli does not strongly validate task parameter names/values. Wrong fields may be silent until MaaCore errors at runtime. For this project, generated configs should be schema-validated and preferably constrained by our own typed model.

## MaaCore Profile Fields

Profiles live under `$MAA_CONFIG_DIR/profiles`; selected by `maa -p/--profile`.

Relevant profile shape:

```toml
[connection]
type = "ADB"
adb_path = "adb"
device = "192.168.5.151:5555"
config = "CompatPOSIXShell"

[resource]
global_resource = ""
platform_diff_resource = ""
user_resource = false

[instance_options]
touch_mode = "MaaTouch"
deployment_with_pause = false
adb_lite_enabled = false
kill_adb_on_exit = false
```

Docs contain a minor naming inconsistency: the Chinese CLI config prose uses `address`, while the copied current `maa-cli` example schema uses `device`. Prefer the schema/example value when generating maa-cli config, then verify with installed `maa` once available.

## Current redroid Relevance

The Linux/container docs list redroid as supported, with Android 11 confirmed in the upstream doc and the requirement that ADB port `5555` be exposed. Our target is redroid 14 at `192.168.5.151`.

Confirmed local probe on 2026-06-26 from CT `115`:

- `192.168.5.151:5555` is reachable.
- `adb connect 192.168.5.151:5555` succeeds.
- Device model: `redroid14_x86_64`.
- Android version: `14`; SDK `34`; ABI `x86_64`.
- SELinux: `Disabled`.
- Resolution: `1280x720`; density `240`.
- Bilibili Arknights package is installed as `com.hypergryph.arknights.bilibili`.
- `adb exec-out screencap -p` produced a valid `1280x720` PNG and no stderr output.

Resolution constraints:

- MAA expects 16:9 landscape, typically `1280x720` or `1920x1080`.
- Non-16:9 devices require forced resolution changes.

Touch mode:

- Android 10+ can break minitouch under SELinux enforcing.
- Prefer testing `MaaTouch` first, then fallback to `ADB` if needed.

Connection config:

- For Linux, maa-cli defaults/prose point to `CompatPOSIXShell`.
- Android docs also mention trying generic/compat/second-resolution/suppress-abnormal-output modes if screenshot or control fails.

## MaaCore Error and Progress Observability

The callback schema is the best structured source of runtime state if the project ever links MaaCore directly.

Global messages:

- `InternalError`
- `InitFailed`
- `ConnectionInfo`
- `AllTasksCompleted`
- `AsyncCallInfo`
- `Destroyed`

Connection `what` values include:

- `ConnectFailed`
- `Connected`
- `UuidGot`
- `UnsupportedResolution`
- `ResolutionError`
- `Reconnecting`
- `Reconnected`
- `Disconnect`
- `ScreencapFailed`
- `TouchModeNotAvailable`

Task messages:

- `TaskChainError`
- `TaskChainStart`
- `TaskChainCompleted`
- `TaskChainExtraInfo`
- `TaskChainStopped`
- `SubTaskError`
- `SubTaskStart`
- `SubTaskCompleted`
- `SubTaskExtraInfo`
- `SubTaskStopped`

Useful subtask details can include `task`, `action`, `exec_times`, `max_times`, `algorithm`, and task-chain identifiers. This is directly relevant to classifying retryable recognition stalls versus fatal task misconfiguration.

## Internal Task Pipeline Notes

`protocol/task-schema.md` describes MaaCore's internal task definitions. This is not the same as maa-cli's custom task TOML, but it explains behavior seen in logs:

- `next`: candidate next tasks, first matched wins.
- `maxTimes`: task execution cap.
- `exceededNext`: where to go after `maxTimes` is reached.
- `onErrorNext`: where to go on execution error.
- `subErrorIgnored`: whether subtask failure aborts parent.
- Recognition algorithms include `MatchTemplate`, `OcrDetect`, `FeatureMatch`, and `JustReturn`.

This means MaaCore already has some internal retry/branching, but it is resource/task-pipeline level behavior. Our framework should treat it as an inner engine and implement outer orchestration around process exit status, logs/callbacks, device state, network state, and desired operational policy.

## Built-In Recovery Worth Noting

`Fight` has a `client_type` parameter documented as enabling restart-and-continue when the game crashes. GUI feature docs also mention:

- automatic reconnect after disconnect or 04:00 daily reset,
- continuing after level-up,
- abandoning and retrying a battle after proxy failure.

These are useful but not sufficient for this project, because the desired behavior includes cross-task retry/fallback, finer scheduling, and failure handling outside MaaCore's current task chain.

## Initial Framework Implications

1. Keep maa-cli as the first integration target.
2. Generate a dedicated `MAA_CONFIG_DIR` inside container-managed state, not under an interactive user's home.
3. Generate profile(s) for target devices, starting with CT `151` redroid 14 at `192.168.5.151:5555`.
4. Generate task files rather than shell-concatenating predefined commands. This preserves maa-cli summaries and condition handling.
5. Always run in batch/noninteractive mode when automation is scheduled.
6. Always request log files and parse stdout/stderr plus log file paths.
7. Classify failures into at least:
   - device unreachable / adb connection failure,
   - unsupported resolution / screenshot failure,
   - touch mode failure,
   - game start failure,
   - task-chain or subtask recognition failure,
   - resource update/network failure,
   - maa-cli/config validation failure,
   - normal no-op/condition skipped,
   - successful completion.
8. Add outer retry policies by failure class, task type, time window, and max attempts.
9. Keep an escape hatch to directly bind MaaCore later if CLI logs are not structured enough.

## Open Questions

- Confirm exact installed maa-cli config schema for the version we install; docs and current examples differ on `address` versus `device`.
- Confirm whether CT `151` exposes ADB at `192.168.5.151:5555` from CT `115`.
- Confirm redroid 14 resolution, orientation, SELinux/touch mode behavior, and whether screenshots contain stderr noise.
- Decide whether first implementation is Python subprocess orchestration or a Rust/Go daemon. Existing repository is Python, but project packaging and long-running scheduling may favor a small service architecture.
