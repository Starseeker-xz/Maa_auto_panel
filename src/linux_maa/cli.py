from __future__ import annotations

import argparse

from linux_maa.game import get_android_download_link, update_game
from linux_maa.maa import run_maa_task
from linux_maa.settings import DEFAULT_DEVICE_SERIAL, DEFAULT_GAME_ID, DEFAULT_TARGET_PACKAGE


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argparse argument parser for linux-maa CLI."""
    parser = argparse.ArgumentParser(prog="linux-maa")
    subparsers = parser.add_subparsers(dest="command", required=True)

    update_parser = subparsers.add_parser("update-game", help="Download and install the latest Bilibili Arknights APK")
    update_parser.add_argument("--serial", default=DEFAULT_DEVICE_SERIAL, help="ADB device serial")
    update_parser.add_argument("--pkg", default=DEFAULT_TARGET_PACKAGE, help="Android package name")
    update_parser.add_argument("--adb", default="adb", help="ADB executable path")
    update_parser.add_argument("--download-dir", default="downloads", help="APK cache directory")
    update_parser.add_argument("--game-id", default=DEFAULT_GAME_ID, help="Biligame game_base_id")
    update_parser.add_argument("--max-cache-versions", type=int, default=3, help="Number of cached APK versions to keep")
    update_parser.add_argument("--force-full", action="store_true", help="Skip incremental patching and download full APK")
    update_parser.add_argument("--no-install", action="store_true", help="Only prepare the APK, do not install it")

    link_parser = subparsers.add_parser("get-download-link", help="Print the latest Android download link")
    link_parser.add_argument("--game-id", default=DEFAULT_GAME_ID, help="Biligame game_base_id")

    run_parser = subparsers.add_parser("run-maa-task", help="Run a maa-cli task with coarse recovery and retries")
    run_parser.add_argument("task", help="maa-cli custom task name")
    run_parser.add_argument("--attempts", type=int, default=3, help="Maximum attempts")
    run_parser.add_argument("--timeout", type=int, default=900, help="Per-attempt timeout in seconds")
    run_parser.add_argument("--serial", default=DEFAULT_DEVICE_SERIAL, help="ADB device serial")
    run_parser.add_argument("--pkg", default=DEFAULT_TARGET_PACKAGE, help="Android package name")
    run_parser.add_argument("--adb", default="adb", help="ADB executable path")
    run_parser.add_argument("--recovery-delay", type=float, default=5.0, help="Seconds to wait after recovery")
    run_parser.add_argument("--no-force-stop", action="store_true", help="Do not force-stop the game between attempts")
    run_parser.add_argument("--profile", default="default", help="maa-cli profile name")

    web_parser = subparsers.add_parser("webui", help="Start the minimal Linux MAA WebUI")
    web_parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    web_parser.add_argument("--port", type=int, default=8000, help="Bind port")
    web_parser.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI args, dispatch to subcommand (update-game, get-download-link, run-maa-task, webui)."""
    args = build_parser().parse_args(argv)

    if args.command == "update-game":
        return update_game(
            serial=args.serial,
            package_name=args.pkg,
            adb_path=args.adb,
            download_dir=args.download_dir,
            game_id=args.game_id,
            max_cache_versions=args.max_cache_versions,
            force_full=args.force_full,
            install=not args.no_install,
        )

    if args.command == "get-download-link":
        link = get_android_download_link(args.game_id)
        if not link:
            print("未能获取下载链接")
            return 1
        print(link)
        return 0

    if args.command == "run-maa-task":
        return run_maa_task(
            args.task,
            attempts=args.attempts,
            timeout_seconds=args.timeout,
            serial=args.serial,
            package_name=args.pkg,
            adb_path=args.adb,
            force_stop=not args.no_force_stop,
            recovery_delay_seconds=args.recovery_delay,
            profile=args.profile,
        )

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
