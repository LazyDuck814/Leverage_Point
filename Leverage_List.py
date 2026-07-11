import os
import json
import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv("token.env")

# --- Gist API ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GIST_ID = os.environ.get("GIST_ID")
GIST_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}
# ----------------


def load_watchlist() -> list:
    if not GITHUB_TOKEN or not GIST_ID:
        print("GITHUB_TOKEN 또는 GIST_ID가 설정되지 않았습니다.")
        return []
    
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        response = requests.get(url, headers=GIST_HEADERS)
        response.raise_for_status()
        
        files = response.json().get("files", {})
        if "watchlist.json" in files:
            return json.loads(files["watchlist.json"]["content"])
        return []
    except Exception as e:
        print(f"Watchlist 로드 실패: {e}")
        return []


def save_watchlist(wl: list) -> None:
    if not GITHUB_TOKEN or not GIST_ID:
        print("GITHUB_TOKEN 또는 GIST_ID가 설정되지 않았습니다.")
        return

    url = f"https://api.github.com/gists/{GIST_ID}"
    payload = {
        "files": {
            "watchlist.json": {
                "content": json.dumps(wl, ensure_ascii=False, indent=2)
            }
        }
    }
    
    try:
        requests.patch(url, headers=GIST_HEADERS, json=payload)
    except Exception as e:
        print(f"Watchlist 저장 실패: {e}")


def get_stock_name(ticker: str) -> str:
    # 6자리 숫자인 경우 한국 주식으로 간주 -> 네이버 금융에서 한글 이름 가져오기
    if ticker.isdigit() and len(ticker) == 6:
        try:
            url = f"https://m.stock.naver.com/api/stock/{ticker}/integration"
            res = requests.get(url, timeout=3)
            return res.json().get('stockName', ticker)
        except Exception:
            return ticker
            
    # 그 외 영문 티커(미국 주식 등)인 경우 -> 야후 파이낸스에서 이름 가져오기
    else:
        try:
            info = yf.Ticker(ticker).info
            return info.get('shortName', ticker)
        except Exception:
            return ticker


def get_watchlist_text(wl: list) -> str:
    if not wl:
        return "관심종목이 비어있습니다."

    text = ""
    for t in wl:
        name = get_stock_name(t)
        text += f"{name} : {t}\n"
        
    return text.strip()