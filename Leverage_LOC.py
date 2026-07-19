import sys
import math
import pandas as pd

from dataclasses import dataclass
from typing import Dict, List, Union
from Leverage_Point import BUFFERED_SIGMA, PERIOD, TICKERS, get_price_data
from Leverage_Point import calculate_bollinger_bands, calculate_rsi, calculate_sigma, calculate_sma

BUFFERED_ORDER = 1.2
LOC_ORDER_AMOUNTS = (200, 200, 200, 400)

@dataclass
class CandidateData:
    rsi14: float
    bb_lower: float
    sma120: float
    daily_return: float


@dataclass
class LocPrices:
    loc1: float
    loc2: float
    loc3: float
    loc4: float


@dataclass
class LocOrder:
    label: str
    target_price: float
    order_price: float
    shares: int


@dataclass
class LocResult:
    ticker: str
    name: str
    latest_date: str
    close: float
    prices: LocPrices
    orders: list[LocOrder]


def get_candidate_data(close: pd.Series, price: float) -> CandidateData:
    previous_close = float(close.iloc[-1])
    next_date = pd.Timestamp(close.index[-1]) + pd.tseries.offsets.BDay(1)
    candidate_close = pd.concat([close, pd.Series([price], index=[next_date])])

    rsi14 = calculate_rsi(candidate_close)
    sma5, sma20, sma60, sma120, sma200 = calculate_sma(candidate_close)
    std20, bb_upper, bb_lower = calculate_bollinger_bands(candidate_close)

    return CandidateData(
        rsi14    = float(rsi14.iloc[-1]),
        bb_lower = float(bb_lower.iloc[-1]),
        sma120   = float(sma120.iloc[-1]),
        daily_return = (price - previous_close) / previous_close,
    )


def find_condition_price(close: pd.Series, condition_func) -> float:
    previous_close = float(close.iloc[-1])
    low_price = 0.000001
    high_price = previous_close

    if condition_func(high_price):
        return high_price

    if not condition_func(low_price):
        return 0.0

    best_price = low_price

    for _ in range(40):
        middle_price = (low_price + high_price) / 2

        if condition_func(middle_price):
            best_price = middle_price
            low_price = middle_price
        else:
            high_price = middle_price

    return best_price


def get_loc_prices(close: pd.Series, years: int) -> LocPrices:
    daily_return = close.pct_change(fill_method=None).dropna().tail(252 * years)
    sigma = calculate_sigma(daily_return)
    buffered_minus_2sigma = sigma.minus_2sigma_pct * BUFFERED_SIGMA / 100

    def check_loc1(price: float) -> bool:
        data = get_candidate_data(close, price)
        return data.sma120 > price and data.daily_return <= buffered_minus_2sigma

    def check_loc2(price: float) -> bool:
        data = get_candidate_data(close, price)
        return data.rsi14 <= 35 and price <= data.bb_lower

    def check_loc3(price: float) -> bool:
        data = get_candidate_data(close, price)
        return data.rsi14 <= 30 and price <= data.bb_lower

    def check_loc4(price: float) -> bool:
        data = get_candidate_data(close, price)
        return data.sma120 > price and data.daily_return <= buffered_minus_2sigma and data.rsi14 <= 30

    return LocPrices(
        loc1 = find_condition_price(close, check_loc1),
        loc2 = find_condition_price(close, check_loc2),
        loc3 = find_condition_price(close, check_loc3),
        loc4 = find_condition_price(close, check_loc4),
    )


def get_loc_orders(prices: LocPrices) -> list[LocOrder]:
    loc_prices = (prices.loc1, prices.loc2, prices.loc3, prices.loc4)
    orders_by_price: dict[float, LocOrder] = {}

    for loc_level, (target_price, order_amount) in enumerate(zip(loc_prices, LOC_ORDER_AMOUNTS), start=1):
        if target_price <= 0:
            continue

        order_price = math.floor(target_price * 100) / 100
        shares = math.floor(order_amount * BUFFERED_ORDER / order_price)

        if order_price in orders_by_price:
            order = orders_by_price[order_price]
            order.label = f"{order.label},{loc_level}"
            order.shares += shares
        else:
            orders_by_price[order_price] = LocOrder(str(loc_level), target_price, order_price, shares)

    orders = list(orders_by_price.values())
    orders.sort(key=lambda order: order.order_price, reverse=True)

    return orders


def get_loc_data(ticker: str, name: str, period: str = PERIOD) -> LocResult:
    years  = int(period.replace("y", ""))
    data   = get_price_data(ticker, f"{years + 1}y")
    close  = data["Close"].squeeze()
    prices = get_loc_prices(close, years)
    orders = get_loc_orders(prices)

    return LocResult(
        ticker      = ticker.upper(),
        name        = name,
        latest_date = pd.Timestamp(close.index[-1]).date().isoformat(),
        close       = float(close.iloc[-1]),
        prices      = prices,
        orders      = orders,
    )


def get_leverage_loc(ticker: Union[str, List[str], Dict[str, str]], period: str = PERIOD) -> List[LocResult]:
    results = []

    if isinstance(ticker, str):
        target_items = [(ticker, ticker)]
    elif isinstance(ticker, dict):
        target_items = ticker.items()
    else:
        target_items = [(ticker, ticker) for ticker in ticker]

    for ticker, name in target_items:
        results.append(get_loc_data(ticker, name, period))

    return results


def build_loc_message(results: List[LocResult]) -> str:
    base_date = results[0].latest_date if results else "-"
    sections = []

    for result in results:
        lines = [
            f"[{result.name}]",
            f"현재가 : {result.close:,.2f}",
            "----------------------------------------------------",
        ]

        for order in result.orders:
            lines.append(f"{order.label}차 LOC 주문가 : {order.order_price:,.2f} | {order.shares}주")

        sections.append("\n".join(lines))

    return f"{base_date}\n\n" + "\n\n".join(sections) + "\n"


if __name__ == "__main__":
    ticker = TICKERS
    period = PERIOD

    if len(sys.argv) >= 2:
        ticker = sys.argv[1].upper()

    if len(sys.argv) >= 3:
        period = f"{sys.argv[2]}y"

    loc_results = get_leverage_loc(ticker=ticker, period=period)
    print(build_loc_message(loc_results))
