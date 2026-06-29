# Session 2026-06-26_1702-setup-maa-cli-test

## Goal

Install `maa-cli` and MaaCore into a project-local runtime layout, initialize configuration from uploaded Windows MAA GUI exports, and attempt a first `test` task run against redroid `192.168.5.151:5555`.

## Initial Findings

- Confirmed: `TEMP/gui.json` is 56,776 bytes and uses the older flattened GUI configuration format.
- Confirmed: `TEMP/gui.new.json` is 23,030 bytes and contains newer structured GUI/task fields including `GUI`, `Timers`, and `VersionUpdate`.
- Confirmed: both uploaded configs have current profile `test`.
- Confirmed: `gui.json` current `test` contains ADB address `192.168.5.151:5555`, client `Bilibili`, touch mode `maatouch`, and selected old GUI queue StartUp/Award/Fight.
- Confirmed: `gui.new.json` current `test` contains structured task queue StartUp, Award, Mall, disabled Infrast, Fight, UserDataUpdate, Recruit.
- Confirmed: `gui.new.json` Infrast task references Windows path `D:\Game\MAA\排班.json`; it was not enabled in the initial CLI test config.

## Active Environment Changes

- Installed project-local `maa-cli` binary at `runtime/maa/bin/maa`.
- Installed MaaCore/resources under project-local XDG directories rooted at `runtime/maa/`.
- Created `scripts/maa-env` to run commands with `PATH`, `MAA_CONFIG_DIR`, `XDG_DATA_HOME`, `XDG_CACHE_HOME`, and `XDG_STATE_HOME` pointing to the project runtime.
- Created live maa-cli profile at `runtime/maa/config/profiles/default.toml`; initially used `MaaTouch`, then changed to `ADB` after Android logcat showed a MaaTouch crash.
- Created live custom test task at `runtime/maa/config/tasks/test.toml`.
- Created diagnostic tasks `runtime/maa/config/tasks/startup-smoke.toml` and `runtime/maa/config/tasks/award-no-mail.toml`.

## Commands and Outcomes

- Ran official `maa-cli` install script with `MAA_INSTALL_DIR=/root/Linux_maa/runtime/maa/bin`; outcome: installed `maa-cli v0.7.5` after checksum verification.
- Ran `maa install` under project-local environment; outcome: installed MaaCore `v6.12.2`, libraries, base resources, and cloned hot-update resources to `runtime/maa/data/maa/MaaResource`.
- Ran `scripts/maa-env maa list`; outcome: CLI detected custom task `test`.
- Ran `scripts/maa-env maa run test --batch --dry-run --log-file=.../maa-test-dry-run.log`; outcome: parsed all five tasks successfully, all reported `Unstarted` as expected for dry-run.
- First real run attempt used invalid CLI syntax `--log-file PATH` and exited with argument error before connecting to MaaCore. Correct syntax is `--log-file=PATH`.
- Started real run with `scripts/maa-env maa run test --batch --log-file=.../maa-test.log`; outcome: exit code 1 after StartUp succeeded and Award/Mall/Fight/Recruit failed.
- Real run summary:
  - `启动 B 服`: `17:06:42 - 17:09:20`, completed.
  - `领取奖励`: `17:09:20 - 17:10:44`, error.
  - `信用商店`: `17:10:45 - 17:11:15`, error.
  - `刷理智`: `17:11:16 - 17:11:20`, error.
  - `自动公招`: `17:11:20 - 17:11:34`, error.
- Detailed MaaCore log path: `runtime/maa/state/maa/debug/asst.log`.
- CLI run log path: `.codex/conversations/2026-06-26_1702-setup-maa-cli-test/scratch/maa-test.log`.
- Failure screenshots copied to scratch:
  - `.codex/conversations/2026-06-26_1702-setup-maa-cli-test/scratch/maa-award-error-raw.png`
  - `.codex/conversations/2026-06-26_1702-setup-maa-cli-test/scratch/maa-mall-error-raw.png`
  - `.codex/conversations/2026-06-26_1702-setup-maa-cli-test/scratch/maa-fight-error-raw.png`
  - `.codex/conversations/2026-06-26_1702-setup-maa-cli-test/scratch/maa-recruit-error-raw.png`

## Intermediate Conclusions

- Confirmed: project-local maa-cli/MaaCore installation and ADB connection work.
- Confirmed: StartUp can launch the Bilibili game client and reach a state MaaCore considers complete.
- Confirmed: StartUp encountered `GameOffline` during launch and clicked repeated offline confirmations before continuing.
- Confirmed: Award entered the mail flow, repeatedly detected loading text `正在提交`, then failed.
- Confirmed: Award failure screenshot is Android launcher/home, not the game UI.
- Likely: Mall/Fight/Recruit failures are cascade failures caused by the game being backgrounded or not returned to a recognized in-game home state after Award failed.
- Confirmed: Android logcat after the run showed `FATAL EXCEPTION: Thread-1` in `com.shxyke.MaaTouch.InputThread.run`, a `NullPointerException` in MaaTouch. This points to the input layer as a likely stability problem.
- Confirmed: Arknights process still existed after the run (`pid 3126`) with `:pushcore` also alive; the game was backgrounded, not fully gone.
- Confirmed: redroid ADB remained reachable; ping to `192.168.5.151` had 0% loss and `192.168.5.151:5555` was open.
- Confirmed: Android memory status was normal; `dumpsys meminfo` reported total RAM about 16 GB and free RAM about 5.1 GB.
- Confirmed: PVE host SSH from CT 115 failed with `Permission denied (publickey,password)`, so `pct status 151` was not available from this session.
- Next promising test: run smaller single tasks with explicit fresh StartUp before each one, and/or run an Award variant with `mail = false` to isolate the mail submission/offline behavior.
- Next promising config work: import the missing Infrast schedule JSON before enabling Infrast.

## Notes

- Added `scripts/maa-env` and `docs/maa-runtime.md`.
- Added live diagnostic task configs `startup-smoke` and `award-no-mail` for future isolation runs.
- Changed live profile touch mode from `MaaTouch` to `ADB`.
- Added `src/linux_maa/maa_runner.py` and `linux-maa run-maa-task`, a coarse retry wrapper around `maa-cli`.

## Runner Prototype

- `linux-maa run-maa-task <task>` runs `runtime/maa/bin/maa run <task> --batch`.
- Each attempt writes a separate log under `runtime/maa/run-logs/`.
- A non-zero maa-cli exit code or subprocess timeout is treated the same way: failure.
- Between attempts the wrapper reconnects ADB, optionally force-stops the game package, sends HOME, waits, and retries.
- Verified with `uv run python -m compileall src` and `uv run linux-maa run-maa-task --help`.

## Current User Direction

- User emphasized the framework goal is to ignore individual instability causes and retry/recover broadly rather than over-diagnosing each failure.
- Implementation should prefer coarse failure handling first: retry, force-stop/start game, reconnect ADB, restart container later, pause/notify after repeated failure.
- User wants the next phase to scaffold the Web UI framework.
- User is not familiar with frontend development and asked for detailed frontend technology guidance.
- Suggested direction for next session: Python FastAPI backend plus React/TypeScript/Vite frontend; avoid Next.js initially; first UI slice should be dashboard/status, task runner, log streaming/history, and config editor placeholder.
- Updated `.gitignore` to ignore `runtime/` and `TEMP/`.
- `diagnose_arknights_crash.py` appeared as deleted in git status during this session, but that was not changed by this session.
