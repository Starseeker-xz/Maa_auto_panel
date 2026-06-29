import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from linux_maa.game_update import get_android_download_link

if __name__ == "__main__":
    link = get_android_download_link()
    if link:
        print(f"找到下载链接: {link}")
    else:
        print("未能获取下载链接")
