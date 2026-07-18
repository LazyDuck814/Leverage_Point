import sys
from dataclasses import dataclass
import pandas as pd
from Leverage_Point import BUFFERED_SIGMA
from Leverage_Point import calculate_bollinger_bands, calculate_rsi, calculate_sigma, calculate_sma, get_price_data

TICKER = "TQQQ"
PERIOD = "1y"

@dataclass
class ScanResult:
    ticker: str              # 종목 코드
    data_start: str          # 스캔 시작일
    data_end: str            # 스캔 종료일
    data_count: int          # 스캔 대상 거래일 수
    mean_return_pct: float   # 분석 기간 일간 수익률 평균
    std_return_pct: float    # 분석 기간 일간 수익률 표준편차
    minus_2sigma_pct: float  # 평균 - 2표준편차
    minus_3sigma_pct: float  # 평균 - 3표준편차
    latest_date: str         # 최신 기준일
    close: float             # 최신 종가
    rsi14: float             # 최신 RSI 14
    scan: pd.DataFrame       # 지표와 조건이 포함된 스캔 결과


def get_scan_data(ticker: str, period: str = PERIOD) -> ScanResult:
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

    sigma = calculate_sigma(df["daily_return"])

    df["below_sma120"] = df["close"] < df["sma120"]
    df["below_minus_2sigma"] = (
        df["daily_return"] * 100 <= sigma.minus_2sigma_pct * BUFFERED_SIGMA
    )
    df["rsi35_or_less"] = df["rsi14"] <= 35
    df["rsi30_or_less"] = df["rsi14"] <= 30
    df["below_bb_lower"] = df["close"] <= df["bb_lower"]

    return ScanResult(
        ticker           = ticker.upper(),
        data_start       = df.index.min().date().isoformat(),
        data_end         = df.index.max().date().isoformat(),
        data_count       = len(df),
        mean_return_pct  = sigma.mean_return_pct,
        std_return_pct   = sigma.std_return_pct,
        minus_2sigma_pct = sigma.minus_2sigma_pct,
        minus_3sigma_pct = sigma.minus_3sigma_pct,
        latest_date      = df.index[-1].date().isoformat(),
        close            = float(df.iloc[-1]["close"]),
        rsi14            = float(df.iloc[-1]["rsi14"]),
        scan             = df,
    )


def get_buy_scan_groups(df: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    cond_sma = df["below_sma120"]
    cond_sigma = df["below_minus_2sigma"]
    cond_rsi35 = df["rsi35_or_less"]
    cond_rsi30 = df["rsi30_or_less"]
    cond_bb_lower = df["below_bb_lower"]

    buy4 = cond_sma & cond_sigma & cond_rsi30
    buy3 = (cond_rsi30 & cond_bb_lower) & ~buy4
    buy2 = (cond_rsi35 & cond_bb_lower) & ~(buy4 | buy3)
    buy1 = (cond_sma & cond_sigma) & ~(buy4 | buy3 | buy2)

    return [
        ("1차 매수 (120일선 아래 & -2σ 이하)",               df[buy1]),
        ("2차 매수 (RSI 35 이하 & BB 하단 이하)",            df[buy2]),
        ("3차 매수 (RSI 30 이하 & BB 하단 이하)",            df[buy3]),
        ("4차 매수 (120일선 아래 & -2σ 이하 & RSI 30 이하)", df[buy4]),
    ]


def build_scan_message(ticker: str, period: str = PERIOD) -> str:
    try:
        result = get_scan_data(ticker, period)
    except Exception as e:
        return f"⚠️ {ticker.upper()} 데이터 조회 실패: {e}"

    lines = [
        f"[{result.ticker}]",
        f"• 기간: {result.data_start} ~ {result.data_end} ({result.data_count}일)",
        f"• 최신 종가: {result.close:,.2f}",
        f"• RSI 지표: {result.rsi14:.2f}",
        f"• 일간 평균 수익: {result.mean_return_pct:.2f}%",
        f"• 일간 표준편차: {result.std_return_pct:.2f}%",
        f"• -2σ 기준: {result.minus_2sigma_pct:.2f}%",
        f"• -3σ 기준: {result.minus_3sigma_pct:.2f}%",
        "----------------------------------------------",
    ]

    for title, target_df in get_buy_scan_groups(result.scan):
        lines.append(title)

        if target_df.empty:
            lines.append("데이터 없음\n")
            continue

        for date, row in target_df.iterrows():
            lines.append(
                f"{date.date()} | "
                f"{row['close']:>6,.2f} | "
                f"{row['daily_return'] * 100:+6.2f}% | "
                f"RSI {row['rsi14']:5.1f} | "
                #f"120일선: {row['sma120']:>7,.2f} | "
                #f"BB하단: {row['bb_lower']:>7,.2f}"
            )
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    ticker = TICKER
    period = PERIOD

    if len(sys.argv) >= 2:
        ticker = sys.argv[1].upper()

    if len(sys.argv) >= 3:
        period = f"{sys.argv[2]}y"

    print(build_scan_message(ticker, period))