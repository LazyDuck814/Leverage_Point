import sys
import pandas as pd

from dataclasses import dataclass
from Leverage_Point import calculate_bollinger_bands, calculate_rsi, calculate_sma, get_price_data

TICKER = "KRW=X"
PERIOD = "1y"

@dataclass
class UsdIndicatorResult:
    ticker: str                    # 환율 (KRW=X)
    latest_date: str               # 분석에 사용한 최신 거래일
    close: float                   # 최신 환율
    daily_return: float            # 전일 대비 수익률
    sma200: float                  # 200일 이동평균선
    bb_lower: float                # 20일 볼린저밴드 하단
    rsi14: float                   # 14일 RSI


@dataclass
class UsdConditions:
    below_sma200: bool             # 환율이 200일선 아래인지
    below_bb_lower: bool           # 환율이 볼린저밴드 하단 이하인지
    rsi35_or_less: bool            # RSI가 35 이하인지


@dataclass
class UsdSignal:
    signal_msg: str                # 신호 조건 설명
    action_text: str               # 실제 행동 문구


@dataclass
class UsdSignalResult:
    indicators: UsdIndicatorResult # 최신 환율 지표 계산 결과
    conditions: UsdConditions      # 환율 매수 조건 판정 결과
    signal: UsdSignal              # 최종 환율 신호


def get_usd_indicator_result(ticker: str = PERIOD, period: str = PERIOD) -> UsdIndicatorResult:
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
        "sma200": sma200,
        "rsi14": rsi14,
        "bb_lower": bb_lower,
    })
    df = df.dropna()
    df = df.tail(252 * years)

    if len(df) < 2:
        raise ValueError(f"{ticker} 계산 가능한 데이터가 부족합니다.")

    latest = df.iloc[-1]

    return UsdIndicatorResult(
        ticker       = ticker.upper(),
        latest_date  = df.index[-1].date().isoformat(),
        close        = float(latest["close"]),
        daily_return = float(latest["daily_return"]),
        sma200       = float(latest["sma200"]),
        bb_lower     = float(latest["bb_lower"]),
        rsi14        = float(latest["rsi14"]),
    )


def get_usd_conditions(indicators: UsdIndicatorResult) -> UsdConditions:
    return UsdConditions(
        below_sma200   = indicators.close < indicators.sma200,
        below_bb_lower = indicators.close <= indicators.bb_lower,
        rsi35_or_less  = indicators.rsi14 <= 35,
    )


def get_usd_signal(conditions: UsdConditions) -> UsdSignal:
    if conditions.rsi35_or_less and conditions.below_bb_lower and conditions.below_sma200:
        return UsdSignal("RSI 35 이하 & BB 하단 이하 & 200일선 아래", "강한 환전 구간")

    elif conditions.rsi35_or_less and conditions.below_bb_lower:
        return UsdSignal("RSI 35 이하 & BB 하단 이하", "약한 환전 구간")

    else:
        return UsdSignal("조건 미충족", "대기")


def get_usd_signal_data(ticker: str = TICKER, period: str = PERIOD) -> UsdSignalResult:
    indicators = get_usd_indicator_result(ticker, period)
    conditions = get_usd_conditions(indicators)
    signal = get_usd_signal(conditions)

    return UsdSignalResult(
        indicators = indicators,
        conditions = conditions,
        signal     = signal,
    )


def build_usd_message(ticker: str = TICKER, period: str = PERIOD) -> str:
    try:
        result = get_usd_signal_data(ticker, period)
    except Exception as e:
        return f"⚠️ 환율 데이터 조회 실패: {e}"

    indicators = result.indicators
    signal = result.signal

    lines = [
        f"기준일 : {indicators.latest_date}\n",
        "[USD/KRW 환율]",
        f"• 현재가(등락률): {indicators.close:,.2f}원 ({indicators.daily_return * 100:+.2f}%)",
        f"• 200일선: {indicators.sma200:,.2f}원",
        f"• RSI: {indicators.rsi14:.1f}",
        f"• BB하단: {indicators.bb_lower:,.2f}원",
        "----------------------------------------------------",
        f">> {signal.signal_msg}",
        f">> {signal.action_text}",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ticker = TICKER
    period = PERIOD

    if len(sys.argv) >= 2:
        ticker = sys.argv[1].upper()

    if len(sys.argv) >= 3:
        period = f"{sys.argv[2]}y"

    print(build_usd_message(ticker=ticker, period=period))
