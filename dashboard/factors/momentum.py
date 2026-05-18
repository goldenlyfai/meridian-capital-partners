"""L2: Momentum factor — 6 sub-factors."""
import pandas as pd
import numpy as np

from data.db import get_conn
from data.market_data import get_prices
from factors.utils import sector_percentile_rank, equal_weight_subscore, winsorize


def _price_return(prices: pd.DataFrame, start_offset: int, end_offset: int) -> float | None:
    """Return from `start_offset` to `end_offset` trading days ago (positive = recent)."""
    if prices.empty or len(prices) < max(start_offset, end_offset):
        return None
    p_end = prices["adj_close"].iloc[-(end_offset + 1)]
    p_start = prices["adj_close"].iloc[-(start_offset + 1)]
    if p_start == 0:
        return None
    return (p_end / p_start) - 1


def compute_momentum(universe_df: pd.DataFrame) -> pd.Series:
    """
    universe_df: DataFrame with columns [ticker, sector].
    Returns composite momentum score 0-100 per ticker (sector-relative).
    """
    conn = get_conn()
    tickers = universe_df["ticker"].tolist()
    sectors = universe_df.set_index("ticker")["sector"]

    sub: dict[str, list] = {
        "ret_12_1": [], "ret_6m": [], "ret_3m": [],
        "accel": [], "high52": [], "rel_str": [],
    }
    index = []

    sector_etf = {
        "Information Technology": "XLK", "Financials": "XLF", "Health Care": "XLV",
        "Energy": "XLE", "Industrials": "XLI", "Communication Services": "XLC",
        "Consumer Discretionary": "XLY", "Consumer Staples": "XLP", "Materials": "XLB",
        "Real Estate": "XLRE", "Utilities": "XLU",
    }

    # Pre-fetch sector ETF returns (252 days)
    etf_ret_6m: dict[str, float] = {}
    for etf in set(sector_etf.values()):
        p = get_prices(conn, etf, days=260)
        if not p.empty and len(p) >= 130:
            ret = (p["adj_close"].iloc[-1] / p["adj_close"].iloc[-130]) - 1
            etf_ret_6m[etf] = ret

    for ticker in tickers:
        prices = get_prices(conn, ticker, days=260)
        if prices.empty or len(prices) < 21:
            for k in sub:
                sub[k].append(np.nan)
            index.append(ticker)
            continue

        # 12-1 month (252 days ago to 21 days ago)
        r121 = _price_return(prices, 252, 21) if len(prices) >= 252 else np.nan
        # 6-month (130 days ago to today)
        r6 = _price_return(prices, 130, 0) if len(prices) >= 130 else np.nan
        # 3-month (65 days ago to today)
        r3 = _price_return(prices, 65, 0) if len(prices) >= 65 else np.nan
        # Acceleration: recent 3m minus prior 3m (65-130 days ago)
        r3_prior = _price_return(prices, 130, 65) if len(prices) >= 130 else np.nan
        accel = (r3 - r3_prior) if (r3 is not None and r3_prior is not None) else np.nan
        # 52-week high proximity
        high52 = prices["high"].tail(252).max() if len(prices) >= 252 else prices["high"].max()
        cur = prices["adj_close"].iloc[-1]
        h52 = (cur / high52) if high52 else np.nan
        # Relative strength vs sector ETF
        sector = sectors.get(ticker)
        etf = sector_etf.get(sector)
        etf_r6 = etf_ret_6m.get(etf, np.nan) if etf else np.nan
        rel_str = (r6 - etf_r6) if (r6 is not None and not np.isnan(etf_r6)) else np.nan

        sub["ret_12_1"].append(r121)
        sub["ret_6m"].append(r6)
        sub["ret_3m"].append(r3)
        sub["accel"].append(accel)
        sub["high52"].append(h52)
        sub["rel_str"].append(rel_str)
        index.append(ticker)

    conn.close()

    df = pd.DataFrame(sub, index=index)
    sec = sectors.reindex(df.index)

    ranked = {}
    for col in df.columns:
        ranked[col] = sector_percentile_rank(winsorize(df[col].dropna().reindex(df.index)), sec)

    score = equal_weight_subscore(list(ranked.values()))
    score.name = "momentum"
    return score
