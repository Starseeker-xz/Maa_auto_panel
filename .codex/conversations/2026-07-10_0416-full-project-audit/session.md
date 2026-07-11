# Session 2026-07-10_0416-full-project-audit

## Scope

- 全量审计当前仓库，不以最近改动为边界。
- 重点评估通用化、扩展其他 maa-cli 类工具、自定义脚本接口，以及架构整合/拆分方向。
- 根目录产出新的综合审计报告；旧审计报告不作为审计输入。
- 审计结束后精简 `.codex` 状态文件，并归档失去未来参考价值的会话记录。

## Working rules

- 审计只依据当前代码、配置、测试、依赖与可执行验证。
- 临时分析产物放入本会话 `scratch/`。
- 未经用户要求不直接实施审计建议中的产品代码重构。

## Verification and observations

- `uvx ruff check src tests`: passed.
- `uv run python -m compileall -q src tests`: passed.
- `.venv/bin/python -m pytest -q`: 66 passed.
- `uvx vulture src tests --min-confidence 80`: no findings.
- `frontend/npm run build`: passed; output JS 768.47 kB (gzip 244.73 kB), Vite emitted the existing >500 kB chunk warning.
- `npm audit --json`: 0 vulnerabilities across the reported frontend dependency tree.
- `pip-audit` reported advisories affecting installed `idna 3.11`, `lxml 6.0.2`, `requests 2.32.5`, `soupsieve 2.8.1`, and `urllib3 2.6.2`; actual exposure differs by call site and is summarized in the audit report.
- `uv run pytest -q` failed before test collection because `.venv/bin/pytest` has stale shebang `#!/root/Linux_maa/.venv/bin/python3` after the repository rename. The interpreter/module invocation works and all tests pass. `uv sync --dry-run` also reports stale installed `linux-maa==0.1.0`.
- Confirmed process timeout defect: a child writing `partial` without newline and sleeping 3s ignored `runtime_kill_seconds=1`; observed elapsed 3.01s, `timed_out=False`, return code 0. Cause is blocking `TextIOWrapper.readline()` after `select()` indicates bytes are readable.
- Live deployment is bound to `0.0.0.0:8000`, has no OpenAPI security scheme, and systemd runs it as root. A scheduled run was active during the audit; it was not interrupted.
- Current local footprint: `history/framework` 2.4M / 44 history files, `debug/framework` 90M. Run history files have no retention deletion; diagnostics do.

## Deliverables and state cleanup

- Replaced root `PROJECT_AUDIT.md` with a new full audit based only on the current working tree and runtime verification.
- Rewrote `.codex/project-history.md` as a compact current-state handoff; removed superseded stage-by-stage implementation chronology.
- Rewrote `.codex/project-lessons.md` to retain only recurring traps that remain applicable.
- Rewrote `.codex/conversations/index.md` to retain three active references: this audit, the authoritative rename session, and the unresolved ADB cold-start investigation.
- Moved all other project conversation directories to `~/.codex/archived_sessions/maa-auto-panel/`. The archive now contains 39 sessions; no session was deleted. The prior archive namespace `linux-maa` was renamed to `maa-auto-panel`.

## Final verification

- `git diff --check`: passed.
- `.venv/bin/python -m pytest -q`: 66 passed.
- `uvx ruff check src tests`: passed.
- `uv run python -m compileall -q src tests`: passed.
- `maa-auto-panel-webui.service`: still active. The real scheduled run observed during the audit later reached `failed` naturally; no audit command stopped or modified it.

## Containerization follow-up

- User clarified that direct root/systemd execution is a test convenience and Docker is the target deployment. Updated the audit so bare-metal root/bind state is evidence about the test mode, not automatically a production defect.
- Added root `CONTAINERIZATION_PLAN.md` for next-session implementation.
- Recommended v1: one non-privileged panel container with its own ADB client/server, external LAN redroid over TCP, bridge networking, one replica, bind/persistent volumes for current runtime and data, and no host network/USB/Docker socket.
- Critical cutover constraint: never run systemd and Compose instances together because scheduler/coordinator/state locks are process-local.
- Superseded by the product-scope correction below: the initial immutable-runtime recommendation was rejected because MAA updates must remain independent from application releases.

## Product-scope correction

- User clarified that MAA updates must not require a new Maa Auto Panel image/release. Revised the plan: `/app/runtime` remains a mutable persistent volume, in-panel maintenance updates remain first-class, and the application image version is independent from maa-cli/MaaCore/resource versions.
- Runtime initialization uses an explicit pinned baseline only for an empty volume; routine container startup never follows latest. Updates require exclusive runtime claim, staged replacement, version verification, and rollback.
- User confirmed the formal threat model is trusted-LAN, single-user. Removed recommendations for login/token/session/RBAC/user database/auth reverse proxy. Compose publishes to the intended LAN address, and firewall/LAN trust is the boundary.
