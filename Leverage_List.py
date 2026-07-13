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


def load_watchlist() -> dict:
    if not GITHUB_TOKEN or not GIST_ID:
        print("GITHUB_TOKEN 또는 GIST_ID가 설정되지 않았습니다.")
        return {}
    
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        response = requests.get(url, headers=GIST_HEADERS)
        response.raise_for_status()
        
        files = response.json().get("files", {})
        if "watchlist.json" in files:
            return json.loads(files["watchlist.json"]["content"])
        return {}
    
    except Exception as e:
        print(f"Watchlist 로드 실패: {e}")
        return {}


def save_watchlist(wl: dict) -> None:
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
    if ticker.isdigit() and len(ticker) == 6:
        try:
            url = f"https://m.stock.naver.com/api/stock/{ticker}/integration"
            res = requests.get(url, timeout=3)
            return res.json().get('stockName', ticker)
        
        except Exception:
            return ticker
            
    else:
        try:
            info = yf.Ticker(ticker).info
            return info.get('shortName', ticker)
        
        except Exception:
            return ticker


def get_watchlist_text(wl: dict) -> str:
    if not wl:
        return "관심종목이 비어있습니다."

    text = "[관심종목]\n"
    for ticker, name in wl.items():
        text += f"• {name} : {ticker}\n"
        
    return text.strip()