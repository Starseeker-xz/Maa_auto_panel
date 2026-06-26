import subprocess
import requests
import os
import re
import sys
import json
import time
from tqdm import tqdm
try:
    import hdiffpatch
except ImportError:
    hdiffpatch = None

class PackageManager:
    def __init__(self, download_dir="downloads", manifest_file="manifest.json", max_cache_versions=3):
        self.download_dir = download_dir
        self.manifest_file = os.path.join(download_dir, manifest_file)
        self.max_cache_versions = max_cache_versions
        
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        self.manifest = self._load_manifest()
        self._cleanup_patch_cache()

    def _load_manifest(self):
        if os.path.exists(self.manifest_file):
            try:
                with open(self.manifest_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"packages": {}}
        return {"packages": {}}

    def _save_manifest(self):
        with open(self.manifest_file, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=4, ensure_ascii=False)

    def get_package_info(self, version):
        return self.manifest["packages"].get(str(version))

    def update_package_status(self, version, status, path=None, url=None, source=None, patch_url=None, patch_path=None):
        version = str(version)
        if version not in self.manifest["packages"]:
            self.manifest["packages"][version] = {}
        
        pkg = self.manifest["packages"][version]
        pkg["status"] = status
        pkg["last_updated"] = time.time()
        if path: pkg["path"] = path
        if url: pkg["url"] = url
        if source: pkg["source"] = source
        if patch_url: pkg["patch_url"] = patch_url
        if patch_path: pkg["patch_path"] = patch_path
        
        self._save_manifest()
        self._cleanup_cache()

    def _cleanup_patch_cache(self):
        if not os.path.exists(self.download_dir):
            return

        for filename in os.listdir(self.download_dir):
            if not (filename.startswith("patch_") and filename.endswith(".diff")):
                continue

            file_path = os.path.join(self.download_dir, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"清理补丁缓存: {file_path}")
                except Exception as e:
                    print(f"清理补丁失败: {e}")

    def _remove_cached_file(self, file_path: str, label: str):
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"清理{label}: {file_path}")
            except Exception as e:
                print(f"清理{label}失败: {e}")

    def _cleanup_cache(self):
        # 保留最近 N 个版本
        packages = self.manifest["packages"]
        if len(packages) <= self.max_cache_versions:
            return

        # 按版本号排序
        sorted_versions = sorted(packages.keys(), key=lambda x: int(x))
        to_remove = sorted_versions[:-self.max_cache_versions]

        for ver in to_remove:
            pkg = packages[ver]
            self._remove_cached_file(pkg.get("path"), "旧版本缓存")
            self._remove_cached_file(pkg.get("patch_path"), "旧补丁缓存")
            del packages[ver]
        
        self._save_manifest()

    def get_verified_package_path(self, version):
        pkg = self.get_package_info(version)
        if pkg and pkg.get("status") == "verified" and os.path.exists(pkg["path"]):
            return pkg["path"]
        return None

class ADBDevice:
    def __init__(self, serial: str):
        self.serial = serial

    def _run_adb(self, args: list) -> subprocess.CompletedProcess:
        cmd = ["adb", "-s", self.serial] + args
        try:
            return subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8')
        except subprocess.CalledProcessError as e:
            print(f"ADB Error: {e.stderr}")
            raise

    def is_connected(self) -> bool:
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=True)
            return self.serial in result.stdout
        except Exception:
            return False

    def connect(self):
        # 尝试连接（针对网络调试）
        if ":" in self.serial:
            subprocess.run(["adb", "connect", self.serial], capture_output=True)

    def get_installed_version_code(self, package_name: str) -> int:
        try:
            # 使用 dumpsys package 获取详细信息
            result = self._run_adb(["shell", "dumpsys", "package", package_name])
            output = result.stdout
            
            # 查找 versionCode
            # 输出格式通常为: versionCode=102 minSdk=... targetSdk=...
            match = re.search(r"versionCode=(\d+)", output)
            if match:
                return int(match.group(1))
            return -1 # 未安装
        except subprocess.CalledProcessError:
            return -1

    def install_apk(self, apk_path: str):
        print(f"正在安装 {apk_path} 到设备 {self.serial} ...")
        # -r: replace existing application
        self._run_adb(["install", "-r", apk_path])
        print("安装完成")

    def get_apk_path(self, package_name: str) -> str:
        try:
            # pm path com.example.app -> package:/data/app/.../base.apk
            result = self._run_adb(["shell", "pm", "path", package_name])
            output = result.stdout.strip()
            if output.startswith("package:"):
                return output.split("package:", 1)[1].strip()
            return ""
        except subprocess.CalledProcessError:
            return ""

    def pull_file(self, remote_path: str, local_path: str) -> bool:
        print(f"正在拉取 {remote_path} -> {local_path} ...")
        try:
            self._run_adb(["pull", remote_path, local_path])
            return True
        except subprocess.CalledProcessError as e:
            print(f"拉取失败: {e}")
            return False

def get_latest_game_info(game_id="101772"):
    url = f"https://line3-h5-mobile-api.biligame.com/game/center/h5/detail/gameinfo/v2?game_base_id={game_id}&sdk_type=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        
        if data["code"] == 0:
            game_data = data["data"]
            info = {
                "game_base_id": game_id,
                "version_code": int(game_data["android_pkg_ver"]),
                "download_link": game_data["download_link"],
                "name": game_data["title"],
                "pkg_name": game_data["android_pkg_name"],
                "incr_updates": []
            }
            
            # 解析增量更新信息
            if "game_incr_pkg" in game_data and "updated_pkg_info_list" in game_data["game_incr_pkg"]:
                info["incr_updates"] = game_data["game_incr_pkg"]["updated_pkg_info_list"]
            
            return info
    except Exception as e:
        print(f"获取游戏信息失败: {e}")
        return None

def build_download_headers(referer=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/vnd.android.package-archive,application/octet-stream;q=0.9,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
        headers["Origin"] = "https://www.biligame.com"
    return headers


def download_file(url, filepath, referer=None):
    headers = build_download_headers(referer)

    try:
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()

        # 检查内容类型，防止下载到错误页面
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            print(f"下载失败: 链接返回了 HTML 页面而不是文件 (Content-Type: {content_type})")
            return False

        total_size_in_bytes = int(response.headers.get('content-length', 0))
        block_size = 1024 * 1024 # 1MB

        progress_bar = tqdm(total=total_size_in_bytes, unit='iB', unit_scale=True)

        with open(filepath, 'wb') as file:
            for data in response.iter_content(block_size):
                progress_bar.update(len(data))
                file.write(data)
        progress_bar.close()

        if total_size_in_bytes != 0 and progress_bar.n != total_size_in_bytes:
            print("ERROR, something went wrong")
            if os.path.exists(filepath):
                os.remove(filepath)
            return False
        return True
    except Exception as e:
        print(f"下载出错: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return False

def ensure_latest_package(manager: PackageManager, game_info: dict) -> str:
    """
    确保本地有最新版本的安装包。
    返回安装包路径，如果失败返回 None。
    """
    remote_ver = game_info["version_code"]
    download_link = game_info["download_link"]
    game_id = game_info.get("game_base_id", "101772")
    referer = f"https://www.biligame.com/detail/?id={game_id}"
    
    # 1. 检查本地是否已有该版本的可用包
    pkg_info = manager.get_package_info(remote_ver)
    if pkg_info:
        if pkg_info["status"] == "verified" and os.path.exists(pkg_info["path"]):
            print(f"本地已有验证过的版本 {remote_ver}: {pkg_info['path']}")
            return pkg_info["path"]
        elif pkg_info["status"] == "unverified" and os.path.exists(pkg_info["path"]):
            print(f"本地有未验证的版本 {remote_ver}，尝试使用...")
            return pkg_info["path"]
        else:
            print(f"本地版本 {remote_ver} 状态异常 ({pkg_info['status']}) 或文件丢失，准备重新获取...")

    # 2. 尝试增量更新策略
    # 查找本地是否有可用的旧版本作为基底
    base_ver = None
    base_path = None
    
    # 遍历增量更新列表，寻找最佳的本地缓存作为基底
    incr_updates = game_info.get("incr_updates", [])
    valid_updates = []

    for update in incr_updates:
        his_ver = int(update["pkg_his_version"])
        # 检查 Manifest 中是否有这个历史版本的 Verified 包
        his_pkg = manager.get_package_info(his_ver)
        if his_pkg and his_pkg["status"] == "verified" and os.path.exists(his_pkg["path"]):
            valid_updates.append({
                "ver": his_ver,
                "path": his_pkg["path"],
                "link": update["pkg_link"]
            })
            
    if valid_updates:
        # 选择版本号最大的作为基底，通常补丁最小
        best_update = max(valid_updates, key=lambda x: x["ver"])
        base_ver = best_update["ver"]
        base_path = best_update["path"]
        incr_link = best_update["link"]
        print(f"发现最佳增量更新路径: {base_ver} -> {remote_ver}")
    
    if base_ver and hdiffpatch:
        print("尝试执行增量更新...")
        patch_filename = f"patch_{base_ver}_to_{remote_ver}.diff"
        patch_path = os.path.join(manager.download_dir, patch_filename)
        new_apk_filename = f"arknights_bilibili_v{remote_ver}_patched.apk"
        new_apk_path = os.path.join(manager.download_dir, new_apk_filename)
        
        # 下载补丁
        print(f"下载补丁: {incr_link}")
        if download_file(incr_link, patch_path, referer=referer):
            try:
                print("正在合并补丁...")
                with open(base_path, "rb") as f: old_data = f.read()
                with open(patch_path, "rb") as f: patch_data = f.read()
                new_data = hdiffpatch.apply(old_data, patch_data)
                
                with open(new_apk_path, "wb") as f: f.write(new_data)
                print("合并成功")
                
                # 记录到 Manifest (状态为 unverified)
                manager.update_package_status(
                    remote_ver, "unverified", 
                    path=new_apk_path, 
                    url=download_link, 
                    source=f"patch_from_{base_ver}",
                    patch_url=incr_link,
                    patch_path=patch_path,
                )
                return new_apk_path
            except Exception as e:
                print(f"增量合并失败: {e}")
                # 增量失败，不立即退出，而是回退到全量
            finally:
                if os.path.exists(patch_path):
                    try:
                        os.remove(patch_path)
                        print(f"清理补丁缓存: {patch_path}")
                    except Exception as e:
                        print(f"清理补丁失败: {e}")
        else:
            print("补丁下载失败")

    # 3. 全量下载策略 (Fallback)
    print("执行全量下载策略...")
    apk_filename = f"arknights_bilibili_v{remote_ver}.apk"
    apk_path = os.path.join(manager.download_dir, apk_filename)
    
    if download_file(download_link, apk_path, referer=referer):
        manager.update_package_status(
            remote_ver, "unverified",
            path=apk_path,
            url=download_link,
            source="full_download"
        )
        return apk_path
    
    return None

def main():
    # device_serial = "127.0.0.1:16416"
    device_serial = "192.168.5.151:5555"
    # device_serial = "emulator-5554"
    target_pkg = "com.hypergryph.arknights.bilibili"
    
    # 初始化包管理器
    manager = PackageManager()

    # 1. 获取远程版本信息
    print("正在获取最新版本信息...")
    game_info = get_latest_game_info()
    if not game_info:
        print("无法获取游戏信息，退出")
        return
    
    remote_ver = game_info["version_code"]
    print(f"最新版本代码: {remote_ver} ({game_info['name']})")

    # 2. 准备安装包
    apk_path = ensure_latest_package(manager, game_info)
    if not apk_path:
        print("无法准备安装包，更新终止")
        return

    game_id = game_info.get("game_base_id", "101772")
    referer = f"https://www.biligame.com/detail/?id={game_id}"

    # 3. 连接设备并检查是否需要安装
    device = ADBDevice(device_serial)
    device.connect()
    
    if not device.is_connected():
        print(f"设备 {device_serial} 未连接，跳过安装步骤")
        return

    local_ver = device.get_installed_version_code(target_pkg)
    if local_ver != -1:
        print(f"设备上已安装版本: {local_ver}")
        if local_ver >= remote_ver:
            print("设备已是最新版本，无需安装")
            # 如果本地包是 unverified，但设备已经是这个版本了，说明可能之前手动安装过
            # 也可以顺便标记为 verified
            manager.update_package_status(remote_ver, "verified", path=apk_path)
            return
    else:
        print("设备未安装该游戏")

    # 4. 执行安装与验证
    print(f"准备安装: {apk_path}")
    try:
        device.install_apk(apk_path)
        print("安装成功！")
        # 标记为已验证
        manager.update_package_status(remote_ver, "verified", path=apk_path)
        
    except Exception as e:
        print(f"安装失败: {e}")
        # 检查是否是增量包导致的问题
        pkg_info = manager.get_package_info(remote_ver)
        if pkg_info and "patch_from" in pkg_info.get("source", ""):
            print("检测到增量包安装失败，尝试回退到全量包...")
            # 标记当前包为 broken 或直接删除记录以便重新获取
            manager.update_package_status(remote_ver, "broken")
            
            # 强制重新获取 (ensure_latest_package 会发现状态不是 verified/unverified，从而重新下载)
            # 但我们需要确保它这次走全量。
            # 简单的方法是：删除本地文件，并且 ensure_latest_package 里的逻辑会因为找不到 verified 的 base 而走全量？
            # 不一定，如果 base 还是 verified，它还会尝试增量。
            # 所以我们需要一种机制强制全量。
            
            # 这里简单处理：手动触发全量下载
            print("正在重新下载全量包...")
            full_apk_filename = f"arknights_bilibili_v{remote_ver}.apk"
            full_apk_path = os.path.join(manager.download_dir, full_apk_filename)
            if download_file(game_info["download_link"], full_apk_path, referer=referer):
                try:
                    device.install_apk(full_apk_path)
                    print("全量包安装成功！")
                    manager.update_package_status(
                        remote_ver, "verified",
                        path=full_apk_path,
                        url=game_info["download_link"],
                        source="full_download_fallback"
                    )
                except Exception as ex:
                    print(f"全量包安装也失败了: {ex}")
            else:
                print("全量包下载失败")
        else:
            print("全量包安装失败，请检查设备状态或 APK 文件完整性。")

if __name__ == "__main__":
    main()

