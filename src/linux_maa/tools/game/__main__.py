"""Standalone CLI entry point for Bilibili Arknights game update/download tools.

Usage:
    python -m linux_maa.tools.game update-game [options]
    python -m linux_maa.tools.game get-download-link [--game-id ID]
"""

from __future__ import annotations

import argparse
import sys

from linux_maa.settings import DEFAULT_DEVICE_SERIAL, DEFAULT_GAME_ID, DEFAULT_TARGET_PACKAGE
from linux_maa.tools.game.update import get_android_download_link, update_game


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m linux_maa.tools.game")
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

    return parser


def main(argv: list[str] | None = None) -> int:
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
            print("无法获取下载链接", file=sys.stderr)
            return 1
        print(link)
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
