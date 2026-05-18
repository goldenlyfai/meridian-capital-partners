"""L4: Transaction cost model — spread + market impact."""
import numpy as np

from data.db import get_conn
from data.market_data import get_prices, get_adv


def estimate_cost_bps(ticker: str, trade_size_usd: float, aum: float) -> float:
    """
    Returns estimated round-trip transaction cost in bps.
    Components: commission (0, Alpaca) + spread + market impact.
    """
    conn = get_conn()
    prices = get_prices(conn, ticker, days=25)
    adv = get_adv(conn, ticker, window=20)
    conn.close()

    if prices.empty:
        return 10.0  # default 10bps if no data

    # Spread cost: 5% of avg daily H-L range
    hl_range = (prices["high"] - prices["low"]).tail(20).mean()
    last_close = prices["close"].iloc[-1]
    spread_bps = (hl_range / last_close) * 0.05 * 10_000

    # Market impact: coef * sqrt(trade/ADV) * daily_vol_bps
    daily_vol = prices["close"].pct_change().tail(20).std()
    daily_vol_bps = daily_vol * 10_000
    if adv > 0:
        impact_bps = 0.10 * np.sqrt(trade_size_usd / adv) * daily_vol_bps
    else:
        impact_bps = 5.0

    total_bps = spread_bps + impact_bps
    return min(total_bps, 50.0)  # cap at 50bps


def cost_adjusted_return(
    expected_return: float,
    ticker: str,
    trade_size_usd: float,
    aum: float,
) -> float:
    """Subtract estimated transaction cost from expected return."""
    bps = estimate_cost_bps(ticker, trade_size_usd, aum)
    cost = bps / 10_000
    return expected_return - cost
