import os
import json
import requests
from dataclasses import dataclass
from typing import List, Dict, Union
import pandas as pd
import yfinance as yf

TICKERS        = ["SOXL", "TQQQ", "QLD"]
CYCLE_TICKERS  = {"TQQQ", "SOXL"}
PERIOD         = "1y"
BUFFERED_SIGMA = 0.95

# --- Gist API ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GIST_ID = os.environ.get("GIST_ID")
GIST_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}
# ----------------

@dataclass
class SignalResult:
    ticker: str              # 종목명 [TQQQ, SOXL, QLD]
    name: str                # 한글 종목명
    latest_date: str         # 분석에 사용한 최신 거래일 날짜
    close: float             # 현재가 or 최신종가
    daily_return_pct: float  # 현재가 기준 전일 종가 대비 등락률 % 단위
    sma5: float              # 5일 이동평균선 가격
    sma20: float             # 20일 이동평균선 가격
    sma120: float            # 120일 이동평균선 가격
    rsi14: float             # 14일 기준 RSI 값
    minus_2sigma_pct: float  # 최근 1년 일간 등락률 기준 -2σ 값 % 단위
    minus_3sigma_pct: float  # 최근 1년 일간 등락률 기준 -3σ 값 % 단위
    below_sma120: bool       # 현재가가 120일선 아래인지 여부
    below_minus_2sigma: bool # 등락률이 -2σ 이하인지 여부
    rsi35_or_less: bool      # RSI가 35 이하인지 여부 (추가됨)
    rsi30_or_less: bool      # RSI가 30 이하인지 여부
    rsi70_or_more: bool      # RSI가 70 이상인지 여부
    rsi75_or_more: bool      # RSI가 75 이상인지 여부
    rsi80_or_more: bool      # RSI가 80 이상인지 여부
    dead_cross: bool         # 5일, 20일 이동평균선 데드크로스 조건 여부
    signal_type: str         # 최종 매매 신호 종류 [BOTH, SIGMA, RSI, SELL70, SELL75, SELL80, NONE]
    signal_msg: str          # 텔레그램 메시지 [120일선, -2σ, RSI 조건 충족]
    action_text: str         # 실제 행동 문구 [매수 구간, 매도 구간]
    in_sell_zone_hold: bool  # 이미 익절 구간 안이지만 신규 돌파는 아닌 상태

    
# signal_state.json 파일을 읽어 기존 매도 사이클 상태를 불러오는 함수
def load_signal_state() -> dict:
    if not GITHUB_TOKEN or not GIST_ID:
        return {}
    
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        response = requests.get(url, headers=GIST_HEADERS)
        response.raise_for_status()
        content = response.json()["files"]["signal_state.json"]["content"]
        return json.loads(content)
    
    except Exception as e:
        print(f"Gist 로드 실패: {e}")
        return {}


# 현재 사이클 상태를 signal_state.json 파일에 저장하는 함수
def save_signal_state(state: dict) -> None:
    if not GITHUB_TOKEN or not GIST_ID:
        return

    url = f"https://api.github.com/gists/{GIST_ID}"
    payload = {
        "files": {
            "signal_state.json": {
                "content": json.dumps(state, ensure_ascii=False, indent=2)
            }
        }
    }
    
    try:
        requests.patch(url, headers=GIST_HEADERS, json=payload)

    except Exception as e:
        print(f"Gist 저장 실패: {e}")


# signal_state.json에서 특정 종목의 상태를 가져오는 함수
def get_ticker_state(state: dict, ticker: str) -> dict:
    ticker = ticker.upper()

    if ticker not in state:
        state[ticker] = {}

    ticker_state = state[ticker]
    ticker_state.setdefault("sold_70", False)
    ticker_state.setdefault("sold_75", False)
    ticker_state.setdefault("sold_80", False)
    ticker_state.setdefault("last_buy_cycle_date", None)

    return ticker_state


# yfinance에서 가격 데이터를 가져오는 함수
def get_price_data(ticker: str, period: str) -> pd.DataFrame:
    data = yf.download(
        ticker,
        period      = period,
        interval    = "1d",
        auto_adjust = False,
        progress    = False
    )

    if data.empty or len(data) < 120:
        raise ValueError(f"{ticker} 데이터가 부족합니다.")

    return data


# 현재가 데이터를 기준으로 RSI를 계산하는 함수
def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


# 등락률 표준편차를 계산하는 함수
def calculate_sigma(returns: pd.Series) -> tuple[float, float, float, float]:
    mean_return = returns.mean()
    std_return = returns.std()

    minus_2sigma = mean_return - 2 * std_return
    minus_3sigma = mean_return - 3 * std_return

    return minus_2sigma, minus_3sigma, mean_return, std_return


# 이동평균선을 구하는 함수
def calculate_sma(close: pd.Series) -> pd.DataFrame:
    sma5   = close.rolling(window=5).mean()
    sma20  = close.rolling(window=20).mean()
    sma120 = close.rolling(window=120).mean()

    df = pd.DataFrame({
        "close"  : close,
        "return" : close.pct_change(fill_method=None),
        "sma5"   : sma5,
        "sma20"  : sma20,
        "sma120" : sma120
    })

    return df


# 최신 데이터와 전일 데이터를 기준으로 매수/매도 조건을 계산하는 함수
def get_conditions(df: pd.DataFrame, minus_2sigma: float) -> tuple[dict, pd.Series, str]:
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    latest_date = df.index[-1].date().isoformat()

    prev_rsi14 = float(prev["rsi14"])

    conditions = {
        "below_sma120"       : bool(latest["close"] < latest["sma120"]),
        "below_minus_2sigma" : bool(latest["return"] <= minus_2sigma * BUFFERED_SIGMA),
        "rsi35_or_less"      : bool(latest["rsi14"] <= 35),
        "rsi30_or_less"      : bool(latest["rsi14"] <= 30),
        "rsi70_or_more"      : bool(latest["rsi14"] >= 70),
        "rsi75_or_more"      : bool(latest["rsi14"] >= 75),
        "rsi80_or_more"      : bool(latest["rsi14"] >= 80),
        "crossed_70_up"      : bool(prev_rsi14 < 70 and latest["rsi14"] >= 70),
        "crossed_75_up"      : bool(prev_rsi14 < 75 and latest["rsi14"] >= 75),
        "crossed_80_up"      : bool(prev_rsi14 < 80 and latest["rsi14"] >= 80),
        "dead_cross"         : bool(prev["sma5"] >= prev["sma20"] and latest["sma5"] < latest["sma20"]),
    }

    return conditions, latest, latest_date


# 하나의 종목에 대해 가격 데이터와 매매 신호를 최종 반환하는 함수
def get_signal_data(ticker: str, name: str, period: str = PERIOD) -> SignalResult:
    years = int(period.replace("y", ""))
    fetch_period = f"{years + 1}y"
    data = get_price_data(ticker, fetch_period)
    close = data["Close"].squeeze()

    df = calculate_sma(close)
    df["rsi14"] = calculate_rsi(close, period=14)
    df = df.dropna()
    df = df.tail(252 * years)

    if len(df) < 2:
        raise ValueError(f"{ticker} 계산 가능한 데이터가 부족합니다.")

    minus_2sigma, minus_3sigma, mean_return, std_return = calculate_sigma(df["return"])

    conditions, latest, latest_date = get_conditions(df, minus_2sigma)

    signal_type, signal_msg, action_text, in_sell_zone_hold = get_signal(ticker, latest_date, conditions)

    return SignalResult(
        ticker             = ticker.upper(),
        name               = name,
        latest_date        = latest_date,
        close              = float(latest["close"]),
        daily_return_pct   = float(latest["return"] * 100),
        sma5               = float(latest["sma5"]),
        sma20              = float(latest["sma20"]),
        sma120             = float(latest["sma120"]),
        rsi14              = float(latest["rsi14"]),
        minus_2sigma_pct   = float(minus_2sigma * 100),
        minus_3sigma_pct   = float(minus_3sigma * 100),
        below_sma120       = conditions["below_sma120"],
        below_minus_2sigma = conditions["below_minus_2sigma"],
        rsi35_or_less      = conditions["rsi35_or_less"],
        rsi30_or_less      = conditions["rsi30_or_less"],
        rsi70_or_more      = conditions["rsi70_or_more"],
        rsi75_or_more      = conditions["rsi75_or_more"],
        rsi80_or_more      = conditions["rsi80_or_more"],
        dead_cross         = conditions["dead_cross"],
        signal_type        = signal_type,
        signal_msg         = signal_msg,
        action_text        = action_text,
        in_sell_zone_hold  = in_sell_zone_hold
    )


# 조건과 매도 사이클 상태를 기준으로 최종 매매 신호를 결정하는 함수
def get_signal(ticker: str, latest_date: str, conditions: dict) -> tuple[str, str, str, bool]:
    signal_type = "NONE"
    signal_msg  = "조건 미충족"
    action_text = "대기"
    in_sell_zone_hold = False

    ticker_upper = ticker.upper()

    if ticker_upper in CYCLE_TICKERS:
        state = load_signal_state()
        ticker_state = get_ticker_state(state, ticker_upper)

        # 1차 매수구간(RSI 35)에 진입하면 사이클 초기화, True를 False로 수정 조건
        buy_signal = (
            (conditions["below_sma120"] and conditions["below_minus_2sigma"])
            or conditions["rsi35_or_less"]
        )

        if buy_signal and ticker_state["last_buy_cycle_date"] != latest_date:
            ticker_state["sold_70"] = False
            ticker_state["sold_75"] = False
            ticker_state["sold_80"] = False
            ticker_state["last_buy_cycle_date"] = latest_date
            save_signal_state(state)

    # 매수 로직 (강한 조건부터 순차적으로 필터링)
    if conditions["below_sma120"] and conditions["below_minus_2sigma"] and conditions["rsi30_or_less"]:
        signal_type = "BUY_3"
        signal_msg  = "120일선, -2σ, RSI 30 이하 조건 모두 충족"
        action_text = "3차 매수구간"

    elif conditions["below_sma120"] and conditions["below_minus_2sigma"]:
        signal_type = "BUY_2_SIGMA"
        signal_msg  = "120일선, -2σ 조건 충족"
        action_text = "2차 매수구간"

    elif conditions["rsi30_or_less"]:
        signal_type = "BUY_2_RSI"
        signal_msg  = "RSI 30 이하 조건 충족"
        action_text = "2차 매수구간"
        
    elif conditions["rsi35_or_less"]:
        signal_type = "BUY_1_RSI"
        signal_msg  = "RSI 35 이하 조건 충족"
        action_text = "1차 매수구간"

    # 매도 로직
    elif ticker_upper in CYCLE_TICKERS:
        if conditions["dead_cross"]:
            signal_type = "SELL_DEADCROSS"
            signal_msg  = "5일선-20일선 데드크로스 발생"
            action_text = "대응구간 : 보유수량 10% 익절"

        elif conditions["crossed_70_up"] and not ticker_state["sold_70"]:
            signal_type = "SELL70"
            signal_msg  = "RSI 70 상향 돌파"
            action_text = "1차 매도구간 : 보유수량 30% 익절"
            ticker_state["sold_70"] = True
            save_signal_state(state)

        elif conditions["crossed_75_up"] and not ticker_state["sold_75"]:
            signal_type = "SELL75"
            signal_msg  = "RSI 75 상향 돌파"
            action_text = "2차 매도구간 : 보유수량 25% 익절"
            ticker_state["sold_75"] = True
            save_signal_state(state)

        elif conditions["crossed_80_up"] and not ticker_state["sold_80"]:
            signal_type = "SELL80"
            signal_msg  = "RSI 80 상향 돌파"
            action_text = "3차 매도구간 : 보유수량 20% 익절"
            ticker_state["sold_80"] = True
            save_signal_state(state)

        elif conditions["rsi70_or_more"]:
            signal_type = "NONE"
            signal_msg  = "기존 매도 구간 유지 중"
            action_text = "추가 행동 없음"
            in_sell_zone_hold = True

    return signal_type, signal_msg, action_text, in_sell_zone_hold


# 텔레그램 메시지 전송하는 함수
def build_point_message(results: List[SignalResult]) -> str:
    base_date = results[0].latest_date if results else "-"

    sections = []

    for result in results:
        lines = [
            f"[{result.name}]",
            f"• 현재가(등락률) : {result.close:,.2f}({result.daily_return_pct:+.2f}%)",
            f"• 120일선(-2σ) : {result.sma120:,.2f}({result.minus_2sigma_pct:+.2f}%)",
            f"• RSI : {result.rsi14:.1f}",
            "----------------------------------------------------",
            f">> {result.signal_msg}",
            f">> {result.action_text}",
        ]
        sections.append("\n".join(lines))

    return (
        f"{base_date}\n\n"
        + "\n\n".join(sections)
    )


# 실행
def get_leverage_point(tickers: Union[List[str], Dict[str, str]], period: str = PERIOD) -> List[SignalResult]:
    results = []
    
    target_items = tickers.items() if isinstance(tickers, dict) else [(t, t) for t in tickers]

    for ticker, name in target_items:
        results.append(get_signal_data(ticker, name, period=period))

    return results