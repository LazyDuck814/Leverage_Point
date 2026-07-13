import sys
from dataclasses import dataclass
import pandas as pd
from Leverage_Point import get_price_data, calculate_indicators

@dataclass
class ScanResult:
    ticker: str               # 종목명
    data_start: str           # 데이터 시작일
    data_end: str             # 데이터 종료일
    data_count: int           # 데이터 총개수, 일봉 단위
    mean_return_pct: float    # 평균 수익률
    std_return_pct: float     # 표준편차
    minus_2sigma_pct: float   # 최근 1년 일간 등락률 기준 -2σ 값
    minus_3sigma_pct: float   # 최근 1년 일간 등락률 기준 -3σ 값
    latest_date: str          # 기준일
    close: float              # 종가
    rsi14: float              # rsi14 값
    scan: pd.DataFrame        # 분석 완료된 전체 데이터 프레임


def get_scan_data(ticker: str = "TQQQ", period: str = "1y") -> ScanResult:
    data = get_price_data(ticker, period)
    
    df, minus_2sigma, minus_3sigma, mean_return, std_return = calculate_indicators(data, ticker)

    df["below_ma120"] = df["close"] < df["ma120"]
    df["below_minus_2sigma"] = df["return"] <= minus_2sigma
    df["rsi35_or_less"] = df["rsi14"] <= 35
    df["rsi30_or_less"] = df["rsi14"] <= 30

    latest_date = df.index[-1].date().isoformat()

    return ScanResult(
        ticker           = ticker.upper(),
        data_start       = data.index.min().date().isoformat(),
        data_end         = data.index.max().date().isoformat(),
        data_count       = len(data),
        mean_return_pct  = float(mean_return * 100),
        std_return_pct   = float(std_return * 100),
        minus_2sigma_pct = float(minus_2sigma * 100),
        minus_3sigma_pct = float(minus_3sigma * 100),
        latest_date      = latest_date,
        close            = float(df.iloc[-1]["close"]),
        rsi14            = float(df.iloc[-1]["rsi14"]),
        scan             = df
    )


def print_scan(ticker: str = "TQQQ", period: str = "1y") -> None:
    result = get_scan_data(ticker, period)
    df = result.scan

    cond_ma = df["below_ma120"]
    cond_sigma = df["below_minus_2sigma"]
    cond_rsi35 = df["rsi35_or_less"]
    cond_rsi30 = df["rsi30_or_less"]

    buy3 = cond_ma & cond_sigma & cond_rsi30
    buy2_sigma = (cond_ma & cond_sigma) & ~buy3
    buy2_rsi = cond_rsi30 & ~buy3
    buy1 = cond_rsi35 & ~(buy3 | buy2_sigma | buy2_rsi)

    scans = [
        ("✅ 1차 매수 (RSI 35 이하 단독)", df[buy1]),
        ("✅ 2차 매수 (RSI 30 이하 단독)", df[buy2_rsi]),
        ("✅ 2차 매수 (120일선 아래 & -2σ 이하)", df[buy2_sigma]),
        ("🔥 3차 매수 (120일선 아래 & -2σ 이하 & RSI 30 이하)", df[buy3]),
    ]

    print(f"종목명        : {result.ticker}")
    print(f"데이터 시작일 : {result.data_start}")
    print(f"데이터 종료일 : {result.data_end}")
    print(f"데이터 개수   : {result.data_count}")
    print(f"최신 종가     : {result.close:,.2f}")
    print(f"RSI 지표      : {result.rsi14:.2f}")
    print(f"1일 평균 등락 : {result.mean_return_pct:.2f}%")
    print(f"1일 표준편차  : {result.std_return_pct:.2f}%")
    print(f"-2σ 기준선    : {result.minus_2sigma_pct:.2f}%")
    print(f"-3σ 기준선    : {result.minus_3sigma_pct:.2f}%")
    print()

    for title, target_df in scans:
        print(f"[{title}]")

        if target_df.empty:
            print("데이터 없음\n")
            continue

        for date, row in target_df.iterrows():
            print(
                f"{date.date()} | "
                f"종가: {row['close']:>7,.2f} | "
                f"등락률: {row['return'] * 100:>+6.2f}% | "
                f"RSI: {row['rsi14']:>5.1f} | "
                f"120일선: {row['ma120']:>7,.2f}"
            )
        print()



def build_scan_message(ticker: str, period: str = "1y") -> str:
    try:
        result = get_scan_data(ticker, period)
    except Exception as e:
        return f"⚠️ {ticker.upper()} 데이터 조회 실패: {e}"

    df = result.scan

    cond_ma = df["below_ma120"]
    cond_sigma = df["below_minus_2sigma"]
    cond_rsi35 = df["rsi35_or_less"]
    cond_rsi30 = df["rsi30_or_less"]

    buy3 = cond_ma & cond_sigma & cond_rsi30
    buy2_sigma = (cond_ma & cond_sigma) & ~buy3
    buy2_rsi = cond_rsi30 & ~buy3
    buy1 = cond_rsi35 & ~(buy3 | buy2_sigma | buy2_rsi)

    scans = [
        ("✅ 1차 매수 (RSI 35 이하 단독)", df[buy1]),
        ("✅ 2차 매수 (RSI 30 이하 단독)", df[buy2_rsi]),
        ("✅ 2차 매수 (120일선 아래 & -2σ 이하)", df[buy2_sigma]),
        ("🔥 3차 매수 (120일선 & -2σ & RSI 30)", df[buy3]),
    ]

    lines = []
    lines.append(f"[{result.ticker}]")
    lines.append(f"• 기간 : {result.data_start} ~ {result.data_end} ({result.data_count}일)")
    lines.append(f"• 최신 종가 : ${result.close:,.2f}")
    lines.append(f"• RSI 지표 : {result.rsi14:.2f}")
    lines.append(f"• 1일 평균 등락 : {result.mean_return_pct:.2f}%")
    lines.append(f"• 1일 표준편차 : {result.std_return_pct:.2f}%")
    lines.append(f"• -2σ 기준선 : {result.minus_2sigma_pct:.2f}%")
    lines.append(f"• -3σ 기준선 : {result.minus_3sigma_pct:.2f}%")
    lines.append("----------------------------------------------")

    for title, target_df in scans:
        lines.append(f"{title}")

        if target_df.empty:
            lines.append("데이터 없음\n")
            continue

        for date, row in target_df.iterrows():
            lines.append(
                f"{date.date()} | "
                f"{row['close']:,.2f} | "
                f"{row['return'] * 100:+7.2f}% | "
                f"RSI {row['rsi14']:.1f} | "
            )
        lines.append("") 

    return "\n".join(lines)


if __name__ == "__main__":
    ticker = "TQQQ"
    period = "1y"

    if len(sys.argv) >= 2:
        ticker = sys.argv[1].upper()

    if len(sys.argv) >= 3:
        period = f"{sys.argv[2]}y"

    print_scan(ticker, period)
