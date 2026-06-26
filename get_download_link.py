import requests
import json
from bs4 import BeautifulSoup

def get_android_download_link():
    game_id = "101772"
    
    # 尝试使用 Bilibili 游戏中心 API 获取数据
    # 这是一个移动端 API，但包含了下载链接信息
    # sdk_type=1 表示 Android
    api_urls = [
        f"https://line3-h5-mobile-api.biligame.com/game/center/h5/detail/gameinfo/v2?game_base_id={game_id}&sdk_type=1",
        f"https://line1-h5-mobile-api.biligame.com/game/center/h5/detail/gameinfo/v2?game_base_id={game_id}&sdk_type=1",
        f"https://line2-h5-mobile-api.biligame.com/game/center/h5/detail/gameinfo/v2?game_base_id={game_id}&sdk_type=1"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
    }

    for api_url in api_urls:
        try:
            print(f"尝试 API: {api_url}")
            response = requests.get(api_url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0 and "data" in data:
                    download_link = data["data"].get("download_link")
                    if download_link:
                        return download_link
        except Exception as e:
            print(f"API {api_url} 调用失败: {e}")

    print("API 调用失败，尝试解析网页（可能失败，因为是动态渲染）...")
    
    # Fallback: 尝试解析网页（虽然已知是 CSR，但保留逻辑）
    url = f"https://www.biligame.com/detail/?id={game_id}"
    desktop_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=desktop_headers)
        soup = BeautifulSoup(response.text, "lxml")
        
        # 尝试查找包含“安卓下载”文本的链接
        links = soup.find_all("a")
        for link in links:
            if "安卓下载" in link.get_text():
                return link.get("href")
                
    except Exception as e:
        print(f"网页解析失败: {e}")

    return None

if __name__ == "__main__":
    link = get_android_download_link()
    if link:
        print(f"找到下载链接: {link}")
    else:
        print("未能获取下载链接")
