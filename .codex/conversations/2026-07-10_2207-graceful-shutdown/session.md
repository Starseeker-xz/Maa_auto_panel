# Session: graceful shutdown

- Session id: `2026-07-10_2207-graceful-shutdown`
- Scope: implement deterministic SIGTERM shutdown for containerization.
- Outcome: complete; production systemd service restored active on final code.

## Implementation

- FastAPI now owns service startup/close through lifespan; scheduler no longer starts in its constructor.
- `WebServices.close()` is the single shutdown orchestrator: scheduler/coordinator/managers enter closing, all active runs receive stop together, share a 60-second deadline, remaining runs receive force-stop and share a 15-second deadline, then diagnostics close.
- `GenericRunManager` rejects starts after closing begins, wakes state waiters, exposes shutdown stop/force and absolute-deadline join.
- `RunCoordinator.begin_shutdown()` wakes blocked resource acquisition and prevents any later lease.
- Scheduler and run threads are named, non-daemon threads and are explicitly joined.
- External commands use a new POSIX session. stop sends SIGTERM to the process group; force-stop sends SIGKILL to the process group, including descendants.
- CLI uses a shutdown-aware Uvicorn Server. SIGTERM broadcasts a process cancellation token before Uvicorn drains connections; SSE checks it at most once per second. Uvicorn retains a 5-second cancellation fallback.
- The custom Server restores original signal handlers without re-raising SIGTERM after successful cleanup, so graceful service/container shutdown returns status 0.
- `/etc/systemd/system/maa-auto-panel-webui.service` now uses `TimeoutStopSec=120`, followed by `systemctl daemon-reload`.

## Verification

- `.venv/bin/python -m pytest -q`: 77 passed.
- `.venv/bin/python -m compileall -q src tests`: passed.
- `git diff --check`: passed.
- Four real `GenericRunManager` instances were stopped through one shared deadline in tests.
- A parent and SIGTERM-ignoring child process were both removed through process-group force-stop.
- Isolated WebUI with a live SSE connection exited about 1 second after SIGTERM with return code 0 and no cancellation traceback.
- Final systemd live-SSE stop: 586 ms, state `inactive`, result `success`, `ExecMainStatus=0`; service then restarted active and `/api/runs/current` returned idle.

## Mistakes and discarded paths

- Starlette `TestClient` could not be used because this environment lacks the new `httpx2` package. Lifespan tests directly enter `app.router.lifespan_context`, avoiding an unnecessary dependency.
- A first implementation relied only on Uvicorn's 5-second graceful timeout. It exited promptly but cancelled SSE with a traceback and non-success service result; retained only as a safety fallback.
- Polling `request.is_disconnected()` alone did not see Uvicorn shutdown early enough through `BaseHTTPMiddleware`. The process-level shutdown token is required to close SSE proactively.
- Uvicorn 0.49 re-raises captured SIGTERM after graceful cleanup. That produced exit status 143 through `uv run`; the custom Server intentionally omits this final re-raise.

## Active environment effects

- `maa-auto-panel-webui.service` is active and running the final lifecycle implementation.
- Its live unit has `TimeoutStopSec=120`.
