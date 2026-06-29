# Session 2026-06-26_1620-maa-cli-framework-docs

## Goal

Prepare the `Linux_maa` project for a future Docker-packaged framework around `maa-cli`/MaaCore with robust retry, fallback, and scheduling behavior. First tasks: update persistent state/memory, inspect the environment, mirror and study MAA Chinese documentation, and maintain a documentation folder for upstream and project docs.

## Environment Facts

- Confirmed: Working directory is `/root/Linux_maa`.
- Confirmed: Hostname from `uname` output is `Dockers`.
- Confirmed: OS is Debian GNU/Linux 12 (bookworm).
- Confirmed: Kernel is `6.8.12-9-pve`.
- Confirmed: Current CT IP is `192.168.5.15/24`; default route is via `192.168.5.10`.
- Confirmed: Docker bridges are present (`docker0` and `br-454ec2ab124b`).
- Confirmed: `python3 --version` returned `Python 3.11.2`.
- Confirmed: `uv` was not available during initial probing.
- Confirmed: `rg` was initially missing.
- Confirmed: `adb`, `nc`, `ping`, and `curl` are available.
- Confirmed: `192.168.5.151:5555` is reachable from CT `115`.
- Confirmed: ADB target `192.168.5.151:5555` reports `redroid14_x86_64`, Android 14, SDK 34, x86_64 ABI, SELinux Disabled, `1280x720`, density 240.
- Confirmed: `com.hypergryph.arknights.bilibili` is installed on redroid CT `151`.
- Confirmed: redroid CT `151` screenshot command produced a valid `1280x720` PNG with empty stderr.

## Commands and Outcomes

- Ran repository/file probes with `find` because `rg` was missing.
- Ran `apt-get update && apt-get install -y ripgrep`; outcome: installed Debian `ripgrep` package successfully.
- Ran `git status --short`; outcome: no tracked/untracked changes before creating `.codex/` and docs directories.
- Ran `git remote -v`, `git branch --show-current`, and `git log --oneline -5`; outcome: `origin` is `git@github.com:Starseeker-xz/Linux_maa.git`, branch `main`, HEAD `da108af`.
- Inspected top-level Python scripts enough to identify existing APK download/update/diagnosis functionality.
- Mirrored MAA Chinese docs from branch `archive/dev-v1` into `docs/maa-upstream/zh-cn/`.
- Copied selected maa-cli schemas and example configs into `docs/maa-cli/`.
- Read first-pass focus docs: CLI install/usage/config, MaaCore integration protocol, callback schema, task-flow schema, connection docs, GUI/newbie/feature docs, Linux/redroid docs.
- Created `docs/README.md` and `docs/maa-reading-notes.md`.
- Ran TCP reachability probes for LAN hosts and redroid ADB ports. `192.168.5.151:5555` is open; `5554` and `5556` are closed/filtered.
- Ran `adb connect 192.168.5.151:5555`; outcome: connected successfully and started local ADB server.
- Ran `adb exec-out screencap -p`; outcome: valid PNG at `scratch/adb/redroid151-screencap.png`, empty stderr at `scratch/adb/redroid151-screencap.stderr`.
- Ran `curl -LsSf https://astral.sh/uv/install.sh | sh`; outcome: installed `uv` and `uvx` to `/root/.local/bin`.
- Ran `uv python install 3.12 && uv sync`; outcome: installed CPython `3.12.13`, created `.venv`, installed project dependencies and editable `linux-maa`.
- Repackaged the update-game functionality into `src/linux_maa/` and added `linux-maa` console script.
- Ran `uv run python -m compileall src update_arknights.py get_download_link.py diagnose_arknights_crash.py`; outcome: success after fixing one indentation error in `src/linux_maa/game_update.py`.
- Ran `uv run linux-maa get-download-link`; outcome: returned `https://pkg.biligame.com/games/mrfz_2.7.41_20260520_100806_91556.apk`.
- Ran direct ADB version query; outcome: installed Bilibili Arknights versionCode `160`, versionName `2.7.41`.
- Ran metadata query through packaged code; outcome: remote Bilibili Arknights versionCode `160`, name `明日方舟`.
- Ran `uv run linux-maa update-game`; outcome: success, no download/install because device already has latest version.
- Ran `uv run python update_arknights.py`; outcome: compatibility wrapper success, no download/install because device already has latest version.
- Ran `uv run python get_download_link.py`; outcome: compatibility wrapper success.

## Active Environment Changes

- Installed system package `ripgrep` via APT in CT `115`; this remains active for future shell sessions.
- Local ADB server was started by `adb connect 192.168.5.151:5555`; this may remain running on port `5037`.
- Installed `uv`/`uvx` into `/root/.local/bin`; shell sessions need `PATH="$HOME/.local/bin:$PATH"` unless profile loading already includes it.
- Created project virtualenv `.venv` with CPython `3.12.13` via `uv sync`.

## Temporary Notes

- Need to mirror/read MAA Chinese docs next, especially protocol docs, maa-cli usage docs, and Windows GUI usage docs.
- User clarified product direction: high-availability Web UI framework around scheduled `maa-cli` execution, log-based failure detection, granular retry/fallback policies, notification/pause behavior, unified visual config editing, external script hooks, Android container lifecycle checks, game APK update, and MaaCore/resource update.
- Direction-level handoff notes were written to `docs/architecture-direction.md`.
