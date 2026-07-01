from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from linux_maa.android import ADBDevice
from linux_maa.settings import (
    BILIGAME_API_URLS,
    DEFAULT_GAME_ID,
    DEFAULT_TARGET_PACKAGE,
    DESKTOP_USER_AGENT,
    MOBILE_USER_AGENT,
)
from linux_maa.utils import write_text_atomic

try:
    import hdiffpatch
except ImportError:
    hdiffpatch = None


@dataclass(frozen=True)
class GameInfo:
    game_base_id: str
    version_code: int
    download_link: str
    name: str
    package_name: str
    incr_updates: list[dict[str, Any]]


class PackageManager:
    def __init__(self, download_dir: str | Path = "downloads", manifest_file: str = "manifest.json", max_cache_versions: int = 3) -> None:
        self.download_dir = Path(download_dir)
        self.manifest_file = self.download_dir / manifest_file
        self.max_cache_versions = max_cache_versions
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = self._load_manifest()
        self._cleanup_patch_cache()

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_file.exists():
            return {"packages": {}}
        try:
            return json.loads(self.manifest_file.read_text(encoding="utf-8"))
        except Exception:
            return {"packages": {}}

    def _save_manifest(self) -> None:
        write_text_atomic(self.manifest_file, json.dumps(self.manifest, indent=4, ensure_ascii=False))

    def get_package_info(self, version: int | str) -> dict[str, Any] | None:
        return self.manifest.setdefault("packages", {}).get(str(version))

    def update_package_status(
        self,
        version: int | str,
        status: str,
        *,
        path: str | Path | None = None,
        url: str | None = None,
        source: str | None = None,
        patch_url: str | None = None,
        patch_path: str | Path | None = None,
    ) -> None:
        version_key = str(version)
        packages = self.manifest.setdefault("packages", {})
        pkg = packages.setdefault(version_key, {})
        pkg["status"] = status
        pkg["last_updated"] = time.time()
        if path is not None:
            pkg["path"] = str(path)
        if url is not None:
            pkg["url"] = url
        if source is not None:
            pkg["source"] = source
        if patch_url is not None:
            pkg["patch_url"] = patch_url
        if patch_path is not None:
            pkg["patch_path"] = str(patch_path)
        self._save_manifest()
        self._cleanup_cache()

    def get_verified_package_path(self, version: int | str) -> Path | None:
        pkg = self.get_package_info(version)
        if not pkg or pkg.get("status") != "verified":
            return None
        path = Path(pkg.get("path", ""))
        return path if path.exists() else None

    def _cleanup_patch_cache(self) -> None:
        for path in self.download_dir.glob("patch_*.diff"):
            try:
                path.unlink()
                print(f"清理补丁缓存: {path}")
            except Exception as exc:
                print(f"清理补丁失败: {exc}")

    def _cleanup_cache(self) -> None:
        packages = self.manifest.setdefault("packages", {})
        if len(packages) <= self.max_cache_versions:
            return

        sorted_versions = sorted(packages.keys(), key=lambda value: int(value))
        for version in sorted_versions[:-self.max_cache_versions]:
            pkg = packages[version]
            self._remove_cached_file(pkg.get("path"), "旧版本缓存")
            self._remove_cached_file(pkg.get("patch_path"), "旧补丁缓存")
            del packages[version]
        self._save_manifest()

    @staticmethod
    def _remove_cached_file(file_path: str | None, label: str) -> None:
        if not file_path:
            return
        path = Path(file_path)
        if not path.exists():
            return
        try:
            path.unlink()
            print(f"清理{label}: {path}")
        except Exception as exc:
            print(f"清理{label}失败: {exc}")


def biligame_referer(game_id: str = DEFAULT_GAME_ID) -> str:
    return f"https://www.biligame.com/detail/?id={game_id}"


def get_latest_game_info(game_id: str = DEFAULT_GAME_ID) -> GameInfo | None:
    headers = {"User-Agent": MOBILE_USER_AGENT}
    params = {"game_base_id": game_id, "sdk_type": "1"}

    for base_url in BILIGAME_API_URLS:
        try:
            response = requests.get(base_url, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            print(f"获取游戏信息失败: {base_url}: {exc}")
            continue

        if payload.get("code") != 0 or "data" not in payload:
            continue

        data = payload["data"]
        return GameInfo(
            game_base_id=game_id,
            version_code=int(data["android_pkg_ver"]),
            download_link=data["download_link"],
            name=data["title"],
            package_name=data["android_pkg_name"],
            incr_updates=data.get("game_incr_pkg", {}).get("updated_pkg_info_list", []),
        )

    return None


def get_android_download_link(game_id: str = DEFAULT_GAME_ID) -> str | None:
    game_info = get_latest_game_info(game_id)
    if game_info:
        return game_info.download_link

    response = requests.get(biligame_referer(game_id), headers={"User-Agent": DESKTOP_USER_AGENT}, timeout=20)
    soup = BeautifulSoup(response.text, "lxml")
    for link in soup.find_all("a"):
        if "安卓下载" in link.get_text():
            return link.get("href")
    return None


def build_download_headers(referer: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": DESKTOP_USER_AGENT,
        "Accept": "application/vnd.android.package-archive,application/octet-stream;q=0.9,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
        headers["Origin"] = "https://www.biligame.com"
    return headers


def download_file(url: str, filepath: str | Path, referer: str | None = None) -> bool:
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with requests.get(url, headers=build_download_headers(referer), stream=True, timeout=60) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type:
                print(f"下载失败: 链接返回了 HTML 页面而不是文件 (Content-Type: {content_type})")
                return False

            total_size = int(response.headers.get("content-length", 0))
            progress_bar = tqdm(total=total_size, unit="iB", unit_scale=True)
            with path.open("wb") as file:
                for chunk in response.iter_content(1024 * 1024):
                    if not chunk:
                        continue
                    progress_bar.update(len(chunk))
                    file.write(chunk)
            progress_bar.close()

        if total_size and path.stat().st_size != total_size:
            print("下载失败: 文件大小与 Content-Length 不一致")
            path.unlink(missing_ok=True)
            return False
        return True
    except Exception as exc:
        print(f"下载出错: {exc}")
        path.unlink(missing_ok=True)
        return False


def ensure_latest_package(manager: PackageManager, game_info: GameInfo, *, force_full: bool = False) -> Path | None:
    remote_ver = game_info.version_code
    referer = biligame_referer(game_info.game_base_id)

    pkg_info = manager.get_package_info(remote_ver)
    if pkg_info and not force_full:
        path = Path(pkg_info.get("path", ""))
        status = pkg_info.get("status")
        if status == "verified" and path.exists():
            print(f"本地已有验证过的版本 {remote_ver}: {path}")
            return path
        if status == "unverified" and path.exists():
            print(f"本地有未验证的版本 {remote_ver}，尝试使用: {path}")
            return path
        print(f"本地版本 {remote_ver} 状态异常 ({status}) 或文件丢失，准备重新获取")

    if not force_full:
        patched = _try_incremental_update(manager, game_info, referer)
        if patched:
            return patched

    return download_full_package(manager, game_info, referer)


def _try_incremental_update(manager: PackageManager, game_info: GameInfo, referer: str) -> Path | None:
    if hdiffpatch is None:
        print("hdiffpatch 不可用，跳过增量更新")
        return None

    valid_updates: list[dict[str, Any]] = []
    for update in game_info.incr_updates:
        history_version = int(update["pkg_his_version"])
        history_path = manager.get_verified_package_path(history_version)
        if history_path:
            valid_updates.append({"version": history_version, "path": history_path, "link": update["pkg_link"]})

    if not valid_updates:
        return None

    best_update = max(valid_updates, key=lambda item: item["version"])
    base_version = best_update["version"]
    remote_version = game_info.version_code
    print(f"发现最佳增量更新路径: {base_version} -> {remote_version}")

    patch_path = manager.download_dir / f"patch_{base_version}_to_{remote_version}.diff"
    new_apk_path = manager.download_dir / f"arknights_bilibili_v{remote_version}_patched.apk"

    print(f"下载补丁: {best_update['link']}")
    if not download_file(best_update["link"], patch_path, referer=referer):
        print("补丁下载失败")
        return None

    try:
        print("正在合并补丁...")
        old_data = Path(best_update["path"]).read_bytes()
        patch_data = patch_path.read_bytes()
        new_apk_path.write_bytes(hdiffpatch.apply(old_data, patch_data))
        print("合并成功")
        manager.update_package_status(
            remote_version,
            "unverified",
            path=new_apk_path,
            url=game_info.download_link,
            source=f"patch_from_{base_version}",
            patch_url=best_update["link"],
            patch_path=patch_path,
        )
        return new_apk_path
    except Exception as exc:
        print(f"增量合并失败: {exc}")
        return None
    finally:
        patch_path.unlink(missing_ok=True)


def download_full_package(manager: PackageManager, game_info: GameInfo, referer: str | None = None) -> Path | None:
    print("执行全量下载策略...")
    apk_path = manager.download_dir / f"arknights_bilibili_v{game_info.version_code}.apk"
    if not download_file(game_info.download_link, apk_path, referer=referer or biligame_referer(game_info.game_base_id)):
        return None

    manager.update_package_status(
        game_info.version_code,
        "unverified",
        path=apk_path,
        url=game_info.download_link,
        source="full_download",
    )
    return apk_path


def update_game(
    *,
    serial: str,
    package_name: str = DEFAULT_TARGET_PACKAGE,
    adb_path: str = "adb",
    download_dir: str | Path = "downloads",
    game_id: str = DEFAULT_GAME_ID,
    max_cache_versions: int = 3,
    force_full: bool = False,
    install: bool = True,
) -> int:
    manager = PackageManager(download_dir=download_dir, max_cache_versions=max_cache_versions)

    print("正在获取最新版本信息...")
    game_info = get_latest_game_info(game_id)
    if not game_info:
        print("无法获取游戏信息，退出")
        return 10

    print(f"最新版本代码: {game_info.version_code} ({game_info.name})")
    device = ADBDevice(serial, adb_path=adb_path)

    if install:
        device.connect()
        if not device.is_connected():
            print(f"设备 {serial} 未连接，跳过安装步骤")
            return 20

        local_version = device.get_installed_version_code(package_name)
        if local_version != -1:
            print(f"设备上已安装版本: {local_version}")
            if local_version >= game_info.version_code:
                print("设备已是最新版本，无需安装")
                cached_path = manager.get_verified_package_path(game_info.version_code)
                if cached_path:
                    manager.update_package_status(game_info.version_code, "verified", path=cached_path)
                return 0
        else:
            print("设备未安装该游戏")

    apk_path = ensure_latest_package(manager, game_info, force_full=force_full)
    if not apk_path:
        print("无法准备安装包，更新终止")
        return 11

    if not install:
        print(f"已准备安装包: {apk_path}")
        return 0

    result = _install_and_verify(device, manager, game_info, package_name, apk_path)
    if result == 0:
        return 0

    pkg_info = manager.get_package_info(game_info.version_code)
    if pkg_info and "patch_from" in pkg_info.get("source", ""):
        print("检测到增量包安装失败，尝试回退到全量包...")
        manager.update_package_status(game_info.version_code, "broken")
        full_apk_path = download_full_package(manager, game_info, biligame_referer(game_info.game_base_id))
        if full_apk_path:
            return _install_and_verify(device, manager, game_info, package_name, full_apk_path, source="full_download_fallback")

    print("安装失败，请检查设备状态或 APK 文件完整性")
    return result


def _install_and_verify(
    device: ADBDevice,
    manager: PackageManager,
    game_info: GameInfo,
    package_name: str,
    apk_path: Path,
    *,
    source: str | None = None,
) -> int:
    print(f"准备安装: {apk_path}")
    try:
        device.install_apk(str(apk_path))
    except Exception as exc:
        print(f"安装失败: {exc}")
        return 30

    installed_version = device.get_installed_version_code(package_name)
    if installed_version < game_info.version_code:
        print(f"安装后版本验证失败: 当前 {installed_version}, 期望至少 {game_info.version_code}")
        return 31

    print(f"安装成功，当前版本: {installed_version}")
    manager.update_package_status(
        game_info.version_code,
        "verified",
        path=apk_path,
        url=game_info.download_link,
        source=source,
    )
    return 0
