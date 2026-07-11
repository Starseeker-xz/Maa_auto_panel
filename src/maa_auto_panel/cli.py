from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
import signal
import threading
from types import FrameType

from maa_auto_panel.branding import APP_WEB_TITLE
from maa_auto_panel.lifecycle import clear_shutdown_request, request_shutdown
from maa_auto_panel.paths import CACHE_DIR_ENV, DATA_DIR_ENV


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argparse argument parser for maa-auto-panel CLI."""
    parser = argparse.ArgumentParser(prog="maa-auto-panel")
    subparsers = parser.add_subparsers(dest="command", required=True)

    web_parser = subparsers.add_parser("webui", help=f"Start the {APP_WEB_TITLE}")
    web_parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    web_parser.add_argument("--port", type=int, default=8000, help="Bind port")
    web_parser.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload")
    web_parser.add_argument("--data-dir", help=f"Framework data root (or {DATA_DIR_ENV})")
    web_parser.add_argument("--cache-dir", help=f"Disposable cache root (or {CACHE_DIR_ENV})")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI args, dispatch to subcommand (webui)."""
    args = build_parser().parse_args(argv)

    if args.command == "webui":
        import uvicorn

        class ShutdownAwareServer(uvicorn.Server):
            def handle_exit(self, sig: int, frame: FrameType | None) -> None:
                request_shutdown()
                super().handle_exit(sig, frame)

            @contextmanager
            def capture_signals(self):
                if threading.current_thread() is not threading.main_thread():
                    yield
                    return
                handled_signals = uvicorn.server.HANDLED_SIGNALS
                original_handlers = {sig: signal.signal(sig, self.handle_exit) for sig in handled_signals}
                try:
                    yield
                finally:
                    for sig, handler in original_handlers.items():
                        signal.signal(sig, handler)

        if args.data_dir:
            os.environ[DATA_DIR_ENV] = args.data_dir
        if args.cache_dir:
            os.environ[CACHE_DIR_ENV] = args.cache_dir

        clear_shutdown_request()
        if args.reload:
            uvicorn.run(
                "maa_auto_panel.web.app:create_app",
                host=args.host,
                port=args.port,
                reload=True,
                factory=True,
                timeout_graceful_shutdown=5,
            )
        else:
            config = uvicorn.Config(
                "maa_auto_panel.web.app:create_app",
                host=args.host,
                port=args.port,
                factory=True,
                timeout_graceful_shutdown=5,
            )
            ShutdownAwareServer(config).run()
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
