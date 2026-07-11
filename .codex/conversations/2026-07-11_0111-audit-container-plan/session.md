# Session 2026-07-11_0111-audit-container-plan

- Started: 2026-07-11T01:11:48Z UTC
- Task: Audit and commit current work, then assess pre-Docker-build considerations.

## Pre-commit audit

- `git diff --check`: passed.
- `.venv/bin/python -m pytest -q`: 77 passed in 3.51s.
- `.venv/bin/python -m compileall -q src tests`: passed.
- `frontend/npm run build`: passed; known 768.47 kB bundle warning remains.
- `frontend/npm audit --audit-level=high`: 0 vulnerabilities.
- `uv lock --check`: passed.
- `uv build --wheel`: passed; wheel stored under this session's `scratch/dist/`.
- Stale `linux_maa`/Linux MAA naming search outside archived audit/session material: no findings.
- Mistake: one combined check used `frontend/` as its working directory while addressing repo-root paths. Re-ran all affected checks from the repository root; no project failure resulted.
- Mistake: `npm audit` was first invoked from the repository root and therefore saw no lockfile. Re-ran it from `frontend/` successfully.

## Container pre-build research

- Committed the audited accumulated work as `fb0595a` (`refactor: prepare application for container deployment`).
- Official Docker/uv docs confirm: use `uv sync --locked --no-dev --no-editable` after complete project copy; reserve `--frozen` for an incomplete/partial dependency layer; use `UV_LINK_MODE=copy` with cache mounts; add `useradd --no-log-init`; build secrets must not use ARG/ENV.
- Bind mounts obscure image contents at the mounted target. Runtime seed/bootstrap must live outside `/app/data` or be downloaded explicitly with a pinned checksum.
- Clean `python:3.12-slim-bookworm` test installed the proposed runtime packages, mounted current runtime/config, then ran `maa version`; it failed after printing maa-cli v0.7.5. The same command fails on the host.
- Confirmed current runtime inconsistency: `libMaaCore.so` needs OpenCV `.411`; `libMaaAdbControlUnit.so` needs `.412`; only `.411` is present. A known-good pinned runtime baseline is required before system-library conclusions or end-to-end container smoke tests.
- User clarified deployment policy: Docker artifacts currently constrain future architecture only. Do not build/up or replace the always-running systemd development service unless explicitly requested. Never run Docker and dev/systemd instances concurrently against the sole redroid/shared state.
- Verified all four official references already exist as tracked offline mirrors. Added their canonical online URLs to `docs/README.md` and `docs/maa-reading-notes.md`: CLI install, usage, config, and MaaCore integration protocol.

## Container implementation

- Added `.dockerignore`, multi-stage `Dockerfile`, `compose.yaml`, and `scripts/container-entrypoint`.
- `docker buildx build --check .`: no warnings. `docker compose config --quiet`: passed.
- `docker compose build --pull panel`: passed; build context 1.80 MB, image `maa-auto-panel:local` sha256 `1e79f47...`, size 325 MB. This local image remains as an active environment effect.
- Final image verified as UID/GID 10001 with backend CLI/import, frontend, schemas, adb, git, and curl available.
- Official runtime install was tested in disposable volume `maa-auto-panel-runtime-smoke`: maa-cli download checksum passed and stable MaaCore/resource install completed, but final `maa version` failed in the clean image. The upstream v6.14.0 Linux tarball contains OpenCV `.411` while `libMaaAdbControlUnit.so` needs `.412`.
- Stopped systemd for an isolated Web smoke using a disposable volume and `127.0.0.1:18000`; homepage passed and SIGTERM produced exit 0. Test container/volume were removed and systemd restored active.
