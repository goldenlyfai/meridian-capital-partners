"""L4: Rolling beta calculation — stock vs SPY."""
import logging

import numpy as np
import pandas as pd

from data.db import get_conn
from data.market_data import get_returns

logger = logging.getLogger(__name__)


def compute_beta(ticker: str, window: int = 60) -> float:
    """Rolling 60-day beta vs SPY."""
    conn = get_conn()
    stock_rets = get_returns(conn, ticker, days=window + 10)
    spy_rets = get_returns(conn, "SPY", days=window + 10)
    conn.close()

    if stock_rets.empty or spy_rets.empty:
        return 1.0

    aligned = pd.concat([stock_rets, spy_rets], axis=1).dropna()
    aligned.columns = ["stock", "spy"]
    aligned = aligned.tail(window)

    if len(aligned) < 10:
        return 1.0

    cov = np.cov(aligned["stock"], aligned["spy"])
    spy_var = np.var(aligned["spy"])
    if spy_var == 0:
        return 1.0
    return float(cov[0, 1] / spy_var)


def compute_portfolio_beta(weights: dict[str, float]) -> tuple[float, float, float]:
    """
    Compute long book beta, short book beta, net portfolio beta.
    weights: {ticker: weight} — positive for longs, negative for shorts.
    """
    long_beta = 0.0
    short_beta = 0.0

    for ticker, w in weights.items():
        beta = compute_beta(ticker)
        if w > 0:
            long_beta += w * beta
        else:
            short_beta += w * beta

    net_beta = long_beta + short_beta
    return long_beta, short_beta, net_beta
