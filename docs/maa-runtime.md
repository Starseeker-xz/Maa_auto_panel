# Project-local MAA runtime

This project keeps downloaded `maa-cli`/MaaCore runtime assets under
`runtime/maa/`. The directory is ignored by git because it contains downloaded
binaries, MaaCore libraries/resources, caches, logs, generated config, and
machine-local state.

Editable maa-cli/framework configuration lives separately under `config/maa/`.

## Layout

- `runtime/maa/bin/maa`: project-local `maa-cli` binary.
- `config/maa`: managed editable configuration (`profiles/`, `tasks/`, `infrast/`, etc.).
- `runtime/maa/generated-configs`: temporary sanitized config generated for `maa-cli`.
- `runtime/maa/data/maa/lib`: MaaCore shared libraries.
- `runtime/maa/data/maa/resource`: bundled MaaCore resources.
- `runtime/maa/data/maa/MaaResource`: hot-update resource repository.
- `runtime/maa/cache/maa`: downloaded archives and metadata cache.
- `runtime/maa/state/maa/debug`: default log directory.

Use `scripts/maa-env` to run `maa` with these paths:

```bash
scripts/maa-env maa version
scripts/maa-env maa list
scripts/maa-env maa run test --batch
```

## Current profile

`config/maa/profiles/default.toml` was initialized from the uploaded
Windows GUI config:

- ADB address: `192.168.5.151:5555`
- client: `Bilibili`
- connection config: `CompatPOSIXShell`
- touch mode: `ADB`
- `kill_adb_on_exit = false`

The Windows GUI config used `General`, Windows ADB paths, and `maatouch`. The
Linux runtime uses the system `adb` from `PATH`, Linux-compatible connection
settings, and ADB touch input. The first real test run showed a MaaTouch-side
`NullPointerException`, so `MaaTouch` is not the default here.

## Current test task

`config/maa/tasks/test.toml` is a first-pass conversion of the uploaded
`test` GUI task queue:

- `StartUp` for Bilibili.
- `Award`.
- `Mall`.
- `Fight` with `CF-8` and fallback/default variant `1-7`, no stones.
- `Recruit`.

The uploaded Infrast task is intentionally not enabled yet because it references
`D:\Game\MAA\排班.json`; that scheduling file still needs to be copied and
converted into `config/maa/infrast/` or a future mounted config volume.

Two smaller diagnostic task files are also present in the live runtime:

- `startup-smoke`: only runs StartUp.
- `award-no-mail`: runs StartUp plus Award with `mail = false`, for isolating
  the mail submission/offline failure seen in the first `test` run.

## Docker direction

For Docker, keep this same split:

- image: install `adb`, `maa-cli`, Python app code, and any framework service.
- volume: mount editable config under `/app/config/maa` and runtime state/cache
  under `/app/runtime/maa` or dedicated data volumes.
- entrypoint: run commands through the same environment variables used by
  `scripts/maa-env`.

## Documentation-first rule

MAA documentation in this repository is detailed and should be the first source
for implementation decisions. Do not start with exploratory trial-and-error for
maa-cli/MaaCore behavior when the local docs cover the area.

Use these references first:

- `docs/maa-upstream/zh-cn/manual/cli/`: maa-cli usage, config layout, task
  files, conditions, profile/static/instance options, and import behavior.
- `docs/maa-upstream/zh-cn/protocol/integration.md`: MaaCore task parameters
  and integration API.
- `docs/maa-upstream/zh-cn/protocol/base-scheduling-schema.md`: custom Infrast
  schedule JSON.
- `docs/maa-upstream/zh-cn/protocol/callback-schema.md`: callback/progress
  events and user-facing status extraction.

If these docs are insufficient or appear stale, inspect the actual MAA/maa-cli
source code before inventing behavior or relying on experiments.
