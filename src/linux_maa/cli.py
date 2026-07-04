from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argparse argument parser for linux-maa CLI."""
    parser = argparse.ArgumentParser(prog="linux-maa")
    subparsers = parser.add_subparsers(dest="command", required=True)

    web_parser = subparsers.add_parser("webui", help="Start the minimal Linux MAA WebUI")
    web_parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    web_parser.add_argument("--port", type=int, default=8000, help="Bind port")
    web_parser.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI args, dispatch to subcommand (webui)."""
    args = build_parser().parse_args(argv)

    if args.command == "webui":
        import uvicorn

        uvicorn.run(
            "linux_maa.web.app:create_app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            factory=True,
        )
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
