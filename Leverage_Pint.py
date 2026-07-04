import os
import json
from dataclasses import dataclass
from typing import List

import pandas as pd
import yfinance as yf

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
STATE_FILE    = os.path.join(BASE_DIR, "signal_state.json")
TICKERS       = ["SOXL", "TQQQ", "QLD"]
CYCLE_TICKERS = {"TQQQ", "SOXL"}
PERIOD        = "1y"

@dataclass
class SignalResult:
    ticker: str              # 종목명 [TQQQ, SOXL, QLD]
    latest_date: str         # 분석에 사용한 최신 거래일 날짜
    close: float             # 현재가 or 최신종가
    daily_return_pct: float  # 현재가 기준 전일 종가 대비 등락률 % 단위
    ma120: float             # 120일 이동평균선 가격
    rsi14: float             # 14일 기준 RSI 값
    minus_2sigma_pct: float  # 최근 1년 일간 등락률 기준 -2σ 값 % 단위
    minus_3sigma_pct: float  # 최근 1년 일간 등락률 기준 -3σ 값 % 단위
    below_ma120: bool        # 현재가가 120일선 아래인지 여부
    below_minus_2sigma: bool # 등락률이 -2σ 이하인지 여부
    rsi30_or_less: bool      # RSI가 30 이하인지 여부
    rsi70_or_more: bool      # RSI가 70 이상인지 여부
    rsi75_or_more: bool      # RSI가 75 이상인지 여부
    rsi80_or_more: bool      # RSI가 80 이상인지 여부
    signal_type: str         # 최종 매매 신호 종류 [BOTH, SIGMA, RSI, SELL70, SELL75, SELL80, NONE]
    signal_message: str      # 텔레그램 메시지 [120일선, -2σ, RSI 조건 충족]
    action_text: str         # 실제 행동 문구 [5주 매수, 15주 매수, 남은 보유수량의 25% 익절, 대기]
    in_sell_zone_hold: bool  # 이미 익절 구간 안이지만 신규 돌파는 아닌 상태

    
# signal_state.json 파일을 읽어 기존 매도 사이클 상태를 불러오는 함수
def load_signal_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


# 현재 사이클 상태를 signal_state.json 파일에 저장하는 함수
def save_signal_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


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


# 현재가 or 종가 데이터를 기준으로 RSI를 계산하는 함수
def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


# yfinance에서 가격 데이터를 가져오는 함수
def get_price_data(ticker: str, period: str) -> pd.DataFrame:
    data = yf.download(
        ticker,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False
    )

    if data.empty or len(data) < 120:
        raise ValueError(f"{ticker} 데이터가 부족합니다.")

    return data


# 등락률, -2σ, -3σ, 120일선, RSI를 계산하는 함수
def calculate_indicators(data: pd.DataFrame, ticker: str) -> tuple[pd.DataFrame, float, float]:
    close = data["Close"].squeeze()
    returns = close.pct_change()

    mean_return = returns.dropna().mean()
    std_return = returns.dropna().std()

    minus_2sigma = mean_return - 2 * std_return
    minus_3sigma = mean_return - 3 * std_return

    ma120 = close.rolling(window=120).mean()
    rsi14 = calculate_rsi(close, period=14)

    df = pd.DataFrame({
        "close": close,
        "return": returns,
        "ma120": ma120,
        "rsi14": rsi14
    }).dropna()

    if len(df) < 2:
        raise ValueError(f"{ticker} 계산 가능한 데이터가 부족합니다.")

    return df, minus_2sigma, minus_3sigma


# 최신 데이터와 전일 데이터를 기준으로 매수/매도 조건을 계산하는 함수
def get_conditions(df: pd.DataFrame, minus_2sigma: float) -> tuple[dict, pd.Series, str]:
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    latest_date = df.index[-1].date().isoformat()

    prev_rsi14 = float(prev["rsi14"])

    conditions = {
        "below_ma120": bool(latest["close"] < latest["ma120"]),
        "below_minus_2sigma": bool(latest["return"] <= minus_2sigma),
        "rsi30_or_less": bool(latest["rsi14"] <= 30),
        "rsi70_or_more": bool(latest["rsi14"] >= 70),
        "rsi75_or_more": bool(latest["rsi14"] >= 75),
        "rsi80_or_more": bool(latest["rsi14"] >= 80),
        "crossed_70_up": bool(prev_rsi14 < 70 and latest["rsi14"] >= 70),
        "crossed_75_up": bool(prev_rsi14 < 75 and latest["rsi14"] >= 75),
        "crossed_80_up": bool(prev_rsi14 < 80 and latest["rsi14"] >= 80),
    }

    return conditions, latest, latest_date


# 조건과 매도 사이클 상태를 기준으로 최종 매매 신호를 결정하는 함수
def get_signal(ticker: str, latest_date: str, conditions: dict) -> tuple[str, str, str, bool]:
    signal_type = "NONE"
    signal_message = "조건 미충족"
    action_text = "대기"
    in_sell_zone_hold = False

    ticker_upper = ticker.upper()

    if ticker_upper in CYCLE_TICKERS:
        state = load_signal_state()
        ticker_state = get_ticker_state(state, ticker_upper)

        buy_signal = (
            (conditions["below_ma120"] and conditions["below_minus_2sigma"])
            or conditions["rsi30_or_less"]
        )

        if buy_signal and ticker_state["last_buy_cycle_date"] != latest_date:
            ticker_state["sold_70"] = False
            ticker_state["sold_75"] = False
            ticker_state["sold_80"] = False
            ticker_state["last_buy_cycle_date"] = latest_date
            save_signal_state(state)

    if conditions["below_ma120"] and conditions["below_minus_2sigma"] and conditions["rsi30_or_less"]:
        signal_type = "BOTH"
        signal_message = "120일선, -2σ, RSI 조건 충족"
        action_text = "15주 매수"

    elif conditions["below_ma120"] and conditions["below_minus_2sigma"]:
        signal_type = "SIGMA"
        signal_message = "120일선, -2σ 조건 충족"
        action_text = "5주 매수"

    elif conditions["rsi30_or_less"]:
        signal_type = "RSI"
        signal_message = "RSI 조건 충족"
        action_text = "5주 매수"

    elif ticker_upper in CYCLE_TICKERS:
        if conditions["crossed_70_up"] and not ticker_state["sold_70"]:
            signal_type = "SELL70"
            signal_message = "RSI 70 상향 돌파"
            action_text = "남은 보유수량의 25% 익절"
            ticker_state["sold_70"] = True
            save_signal_state(state)

        elif conditions["crossed_75_up"] and not ticker_state["sold_75"]:
            signal_type = "SELL75"
            signal_message = "RSI 75 상향 돌파"
            action_text = "남은 보유수량의 25% 익절"
            ticker_state["sold_75"] = True
            save_signal_state(state)

        elif conditions["crossed_80_up"] and not ticker_state["sold_80"]:
            signal_type = "SELL80"
            signal_message = "RSI 80 상향 돌파"
            action_text = "남은 보유수량의 25% 익절"
            ticker_state["sold_80"] = True
            save_signal_state(state)

        elif conditions["rsi70_or_more"]:
            signal_type = "NONE"
            signal_message = "기존 익절 구간 유지 중"
            action_text = "추가 행동 없음"
            in_sell_zone_hold = True

    return signal_type, signal_message, action_text, in_sell_zone_hold


# 하나의 종목에 대해 가격 데이터와 매매 신호를 최종 반환하는 함수
def get_signal_data(ticker: str = "TQQQ", period: str = PERIOD) -> SignalResult:
    data = get_price_data(ticker, period)

    df, minus_2sigma, minus_3sigma = calculate_indicators(data, ticker)

    conditions, latest, latest_date = get_conditions(df, minus_2sigma)

    signal_type, signal_message, action_text, in_sell_zone_hold = get_signal(
        ticker=ticker,
        latest_date=latest_date,
        conditions=conditions
    )

    return SignalResult(
        ticker=ticker.upper(),
        latest_date=latest_date,
        close=float(latest["close"]),
        daily_return_pct=float(latest["return"] * 100),
        ma120=float(latest["ma120"]),
        rsi14=float(latest["rsi14"]),
        minus_2sigma_pct=float(minus_2sigma * 100),
        minus_3sigma_pct=float(minus_3sigma * 100),
        below_ma120=conditions["below_ma120"],
        below_minus_2sigma=conditions["below_minus_2sigma"],
        rsi30_or_less=conditions["rsi30_or_less"],
        rsi70_or_more=conditions["rsi70_or_more"],
        rsi75_or_more=conditions["rsi75_or_more"],
        rsi80_or_more=conditions["rsi80_or_more"],
        signal_type=signal_type,
        signal_message=signal_message,
        action_text=action_text,
        in_sell_zone_hold=in_sell_zone_hold
    )


# 실행
def get_leverage_pint(tickers: List[str], period: str = PERIOD) -> List[SignalResult]:
    results = []

    for ticker in tickers:
        results.append(get_signal_data(ticker, period=period))

    return results


# 텔레그램 메시지 전송하는 함수
def build_message(results: List[SignalResult]) -> str:
    base_date = results[0].latest_date if results else "-"

    sections = []

    for result in results:
        lines = [
            f"[{result.ticker}]",
            f"• 현재가(등락률) : {result.close:.2f}({result.daily_return_pct:+.2f}%)",
            f"• 120일선(-2σ) : {result.ma120:.2f}({result.minus_2sigma_pct:+.2f}%)",
            f"• RSI : {result.rsi14:.1f}",
            "----------------------------------------------------",
            f">> {result.signal_message}",
            f">> {result.action_text}",
        ]
        sections.append("\n".join(lines))

    return (
        f"[레버리지 핀트]\n"
        f"{base_date}\n\n"
        + "\n\n".join(sections)
    )


if __name__ == "__main__":
    results = get_leverage_pint(tickers=TICKERS, period=PERIOD)
    message = build_message(results)
    print(message)