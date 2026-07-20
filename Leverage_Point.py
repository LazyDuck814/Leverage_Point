import json
import os
import sys
import pandas as pd
import requests
import yfinance as yf

from dataclasses import dataclass
from typing import Dict, List, Union

PERIOD = "1y"
TICKERS = ["SOXL", "TQQQ", "QLD"]
CYCLE_TICKERS = {"TQQQ", "SOXL"}
BUFFERED_SIGMA = 0.95

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GIST_ID = os.environ.get("GIST_ID")
GIST_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

@dataclass
class IndicatorResult:
    ticker: str                     # 종목 코드
    name: str                       # 종목명
    latest_date: str                # 분석에 사용한 최신 거래일
    close: float                    # 최신 종가
    daily_return: float             # 전일 대비 수익률
    sma5: float                     # 5일 이동평균선
    sma20: float                    # 20일 이동평균선
    sma120: float                   # 120일 이동평균선
    rsi14: float                    # 14일 RSI
    bb_lower: float                 # 20일 볼린저밴드 하단
    prev_sma5: float                # 전일 5일 이동평균선
    prev_sma20: float               # 전일 20일 이동평균선
    prev_rsi14: float               # 전일 14일 RSI


@dataclass
class SigmaResult:
    mean_return_pct: float          # 분석 기간 일간 수익률 평균(% 단위)
    std_return_pct: float           # 분석 기간 일간 수익률 표준편차(% 단위)
    minus_2sigma_pct: float         # 평균 - 2표준편차(% 단위)
    minus_3sigma_pct: float         # 평균 - 3표준편차(% 단위)


@dataclass
class SignalConditions:
    below_sma120: bool              # 종가가 120일선 아래인지
    below_minus_2sigma: bool        # 일간 수익률이 보정 -2시그마 이하인지
    below_bb_lower: bool            # 종가가 볼린저밴드 하단 이하인지
    rsi35_or_less: bool             # RSI가 35 이하인지
    rsi30_or_less: bool             # RSI가 30 이하인지
    rsi70_or_more: bool             # RSI가 70 이상인지
    crossed_70_down: bool           # RSI가 70을 하향 이탈했는지
    crossed_75_down: bool           # RSI가 75를 하향 이탈했는지
    crossed_80_down: bool           # RSI가 80을 하향 이탈했는지
    dead_cross: bool                # 5일선이 20일선을 하향 이탈했는지


@dataclass
class TradeSignal:
    signal_type: str                # 신호 코드
    signal_msg: str                 # 신호 조건 설명
    action_text: str                # 실제 행동 문구
    in_sell_zone_hold: bool = False # 이미 매도 구간 안에 머무는 상태인지


@dataclass
class SignalResult:
    indicators: IndicatorResult     # 최신 지표 계산 결과
    sigma: SigmaResult              # 수익률 시그마 계산 결과
    conditions: SignalConditions    # 매수/매도 조건 판정 결과
    signal: TradeSignal             # 최종 매매 신호


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
        response = requests.patch(url, headers=GIST_HEADERS, json=payload, timeout=10)
        response.raise_for_status()

    except Exception as e:
        print(f"Gist 저장 실패: {e}")


def get_signal_state(state: dict, ticker: str) -> dict:
    ticker = ticker.upper()

    if ticker not in state:
        state[ticker] = {}

    ticker_state = state[ticker]
    ticker_state.setdefault("sold_70", False)
    ticker_state.setdefault("sold_75", False)
    ticker_state.setdefault("sold_80", False)
    ticker_state.setdefault("last_buy_cycle_date", None)

    return ticker_state


def get_price_data(ticker: str, period: str) -> pd.DataFrame:
    data = yf.download(
        ticker,
        period      = period,
        interval    = "1d",
        auto_adjust = False,
        progress    = False,
        threads     = False,
    )

    if data.empty or len(data) < 120:
        raise ValueError(f"{ticker} 데이터가 부족합니다.")

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    if "Close" not in data.columns:
        raise ValueError(f"{ticker} 종가(Close) 데이터를 찾을 수 없습니다.")

    return data


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_sma(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    sma5   = close.rolling(window=5).mean()
    sma20  = close.rolling(window=20).mean()
    sma60  = close.rolling(window=60).mean()
    sma120 = close.rolling(window=120).mean()
    sma200 = close.rolling(window=200).mean()

    return sma5, sma20, sma60, sma120, sma200


def calculate_bollinger_bands(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    sma20 = close.rolling(window=20).mean()
    std20 = close.rolling(window=20).std(ddof=0)

    bb_upper = sma20 + (2 * std20)
    bb_lower = sma20 - (2 * std20)

    return std20, bb_upper, bb_lower


def calculate_sigma(returns: pd.Series) -> SigmaResult:
    mean_return = returns.mean()
    std_return  = returns.std()

    minus_2sigma = mean_return - 2 * std_return
    minus_3sigma = mean_return - 3 * std_return

    return SigmaResult(
        mean_return_pct  = mean_return  * 100,
        std_return_pct   = std_return   * 100,
        minus_2sigma_pct = minus_2sigma * 100,
        minus_3sigma_pct = minus_3sigma * 100,
    )


def get_indicator_sigma_result(ticker: str, name: str, period: str = PERIOD) -> tuple[IndicatorResult, SigmaResult]:
    years = int(period.replace("y", ""))
    data = get_price_data(ticker, f"{years + 1}y")
    close = data["Close"].squeeze()
    daily_return = close.pct_change(fill_method=None)

    sma5, sma20, sma60, sma120, sma200 = calculate_sma(close)
    rsi14 = calculate_rsi(close)
    std20, bb_upper, bb_lower = calculate_bollinger_bands(close)

    df = pd.DataFrame({
        "close": close,
        "daily_return": daily_return,
        "sma5": sma5,
        "sma20": sma20,
        "sma60": sma60,
        "sma120": sma120,
        "sma200": sma200,
        "rsi14": rsi14,
        "std20": std20,
        "bb_lower": bb_lower,
    })
    df = df.dropna()
    df = df.tail(252 * years)

    if len(df) < 2:
        raise ValueError(f"{ticker} 계산 가능한 데이터가 부족합니다.")

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    sigma = calculate_sigma(df["daily_return"])
    indicators = IndicatorResult(
        ticker       = ticker.upper(),
        name         = name,
        latest_date  = df.index[-1].date().isoformat(),
        close        = float(latest["close"]),
        daily_return = float(latest["daily_return"]),
        sma5         = float(latest["sma5"]),
        sma20        = float(latest["sma20"]),
        sma120       = float(latest["sma120"]),
        rsi14        = float(latest["rsi14"]),
        bb_lower     = float(latest["bb_lower"]),
        prev_sma5    = float(previous["sma5"]),
        prev_sma20   = float(previous["sma20"]),
        prev_rsi14   = float(previous["rsi14"]),
    )

    return indicators, sigma


def get_conditions(indicators: IndicatorResult, sigma: SigmaResult) -> SignalConditions:
    return SignalConditions(
        below_sma120       = indicators.close < indicators.sma120,
        below_minus_2sigma = indicators.daily_return * 100 <= sigma.minus_2sigma_pct * BUFFERED_SIGMA,
        below_bb_lower     = indicators.close <= indicators.bb_lower,
        rsi35_or_less      = indicators.rsi14 <= 35,
        rsi30_or_less      = indicators.rsi14 <= 30,
        rsi70_or_more      = indicators.rsi14 >= 70,
        crossed_70_down    = indicators.prev_rsi14 >= 70 and indicators.rsi14 < 70,
        crossed_75_down    = indicators.prev_rsi14 >= 75 and indicators.rsi14 < 75,
        crossed_80_down    = indicators.prev_rsi14 >= 80 and indicators.rsi14 < 80,
        dead_cross         = indicators.prev_sma5 >= indicators.prev_sma20 and indicators.sma5 < indicators.sma20,
    )


def get_buy_signal(conditions: SignalConditions) -> TradeSignal:
    if conditions.below_sma120 and conditions.below_minus_2sigma and conditions.rsi30_or_less:
        return TradeSignal("BUY_4", "120일선, -2σ, RSI 30 조건 모두 충족", "4차 매수구간")

    elif conditions.rsi30_or_less and conditions.below_bb_lower:
        return TradeSignal("BUY_3", "RSI 30, 볼린저밴드 조건 충족", "3차 매수구간")

    elif conditions.rsi35_or_less and conditions.below_bb_lower:
        return TradeSignal("BUY_2", "RSI 35, 볼린저밴드 조건 충족", "2차 매수구간")

    elif conditions.below_sma120 and conditions.below_minus_2sigma:
        return TradeSignal("BUY_1", "120일선, -2σ 조건 충족", "1차 매수구간")

    else:
        return TradeSignal("NONE", "조건 미충족", "대기")
    

def get_sell_signal(conditions: SignalConditions, ticker_state: dict) -> TradeSignal:
    if conditions.dead_cross:
        return TradeSignal("SELL_DEADCROSS", "5일선-20일선 데드크로스 발생", "조정구간: 보유수량 20% 익절")

    elif conditions.crossed_70_down and not ticker_state["sold_70"]:
        return TradeSignal("SELL70", "RSI 70 하향 이탈", "1차 매도구간: 보유수량 30% 익절")

    elif conditions.crossed_75_down and not ticker_state["sold_75"]:
        return TradeSignal("SELL75", "RSI 75 하향 이탈", "2차 매도구간: 보유수량 25% 익절")

    elif conditions.crossed_80_down and not ticker_state["sold_80"]:
        return TradeSignal("SELL80", "RSI 80 하향 이탈", "3차 매도구간: 보유수량 20% 익절")

    elif conditions.rsi70_or_more:
        return TradeSignal("NONE", "기존 매도 구간 유지 중", "추가 행동 없음", True)

    else:
        return TradeSignal("NONE", "조건 미충족", "대기")


def get_signal_data(ticker: str, name: str, period: str = PERIOD, state: dict | None = None) -> SignalResult:
    indicators, sigma = get_indicator_sigma_result(ticker, name, period)
    conditions = get_conditions(indicators, sigma)

    loaded_state = state if state is not None else load_signal_state()
    ticker_upper = ticker.upper()
    state_changed = False

    signal = get_buy_signal(conditions)

    if ticker_upper in CYCLE_TICKERS:
        ticker_state = get_signal_state(loaded_state, ticker_upper)

        buy_cycle_started = (
            (conditions.below_sma120 and conditions.below_minus_2sigma) 
            or (conditions.rsi35_or_less and conditions.below_bb_lower)
        )

        if buy_cycle_started and ticker_state["last_buy_cycle_date"] != indicators.latest_date:
            ticker_state["sold_70"] = False
            ticker_state["sold_75"] = False
            ticker_state["sold_80"] = False
            ticker_state["last_buy_cycle_date"] = indicators.latest_date
            state_changed = True

        if signal.signal_type == "NONE":
            signal = get_sell_signal(conditions, ticker_state)

            if signal.signal_type == "SELL70":
                ticker_state["sold_70"] = True
                state_changed = True

            elif signal.signal_type == "SELL75":
                ticker_state["sold_75"] = True
                state_changed = True

            elif signal.signal_type == "SELL80":
                ticker_state["sold_80"] = True
                state_changed = True

    if state is None and state_changed:
        save_signal_state(loaded_state)

    return SignalResult(
        indicators = indicators,
        sigma      = sigma,
        conditions = conditions,
        signal     = signal
    )


def build_point_message(results: List[SignalResult]) -> str:
    base_date = results[0].indicators.latest_date if results else "-"
    sections = []

    for result in results:
        indicators = result.indicators
        sigma = result.sigma
        signal = result.signal

        lines = [
            f"[{indicators.name}]",
            f"• 현재가(등락률): {indicators.close:,.2f} ({indicators.daily_return * 100:+.2f}%)",
            f"• 120일선(-2σ): {indicators.sma120:,.2f} ({sigma.minus_2sigma_pct:+.2f}%)",
            f"• RSI: {indicators.rsi14:.1f}",
            f"• BB하단: {indicators.bb_lower:,.2f}",
            "----------------------------------------------------",
            f">> {signal.signal_msg}",
            f">> {signal.action_text}",
        ]
        sections.append("\n".join(lines))

    return f"기준일 : {base_date}\n\n" + "\n\n".join(sections) + "\n"


def get_leverage_point(ticker: Union[str, List[str], Dict[str, str]], period: str = PERIOD) -> List[SignalResult]:
    state = load_signal_state()
    before_state = json.dumps(state, sort_keys=True)
    results = []

    if isinstance(ticker, str):
        target_items = [(ticker, ticker)]
    elif isinstance(ticker, dict):
        target_items = ticker.items()
    else:
        target_items = [(ticker, ticker) for ticker in ticker]

    for ticker, name in target_items:
        results.append(get_signal_data(ticker, name, period=period, state=state))

    after_state = json.dumps(state, sort_keys=True)

    if before_state != after_state:
        save_signal_state(state)

    return results


if __name__ == "__main__":
    ticker = TICKERS
    period = PERIOD

    if len(sys.argv) >= 2:
        ticker = sys.argv[1].upper()

    if len(sys.argv) >= 3:
        period = f"{sys.argv[2]}y"

    results = get_leverage_point(ticker=ticker, period=period)
    print(build_point_message(results))