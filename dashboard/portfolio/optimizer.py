"""L4: Conviction-tilt optimizer — equal weight base with score-based tilts."""
import logging

import pandas as pd

from data.db import get_conn
from data.market_data import get_adv
from data.earnings_calendar import has_earnings_soon
from portfolio.beta import compute_beta, compute_portfolio_beta

logger = logging.getLogger(__name__)


def conviction_optimize(
    long_candidates: pd.DataFrame,
    short_candidates: pd.DataFrame,
    aum: float,
    cfg: dict,
) -> dict[str, float]:
    """
    Build target weights using conviction-tilt method.
    Returns {ticker: weight} — positive for longs, negative for shorts.
    """
    conn = get_conn()
    weights = {}

    for book, candidates, sign in [
        ("long", long_candidates, +1),
        ("short", short_candidates, -1),
    ]:
        if candidates.empty:
            continue

        n = len(candidates)
        base_w = cfg[f"target_{'long' if sign > 0 else 'short'}_gross"] / n

        top5_threshold = candidates["composite"].quantile(0.95)
        top10_threshold = candidates["composite"].quantile(0.90)

        for ticker, row in candidates.iterrows():
            score = row["composite"]

            # Conviction tilt
            if score >= top5_threshold:
                w = base_w * cfg["conviction_tilt"]["top5pct_multiplier"]
            elif score >= top10_threshold:
                w = base_w * cfg["conviction_tilt"]["top10pct_multiplier"]
            else:
                w = base_w

            # Liquidity: no position > 5% of 20-day ADV
            adv = get_adv(conn, ticker, window=20)
            if adv > 0:
                max_from_adv = adv * cfg["liquidity"]["max_adv_pct"]
                w = min(w, max_from_adv / aum)

            # Earnings blackout: halve size if earnings in 5 days
            if has_earnings_soon(conn, ticker, days=5):
                w *= cfg["liquidity"]["earnings_size_reduction"]
                logger.info("Earnings soon: halving position %s", ticker)

            # Max position cap
            w = min(w, cfg["max_position_pct"])

            weights[ticker] = sign * w

    conn.close()

    # Beta adjustment: scale so net beta ≈ 0
    long_beta, short_beta, net_beta = compute_portfolio_beta(weights)
    logger.info("Pre-adjustment betas — long: %.2f, short: %.2f, net: %.2f",
                long_beta, short_beta, net_beta)

    max_beta = cfg.get("max_net_beta", 0.15)
    if abs(net_beta) > max_beta:
        # Scale short book to reduce net beta
        scale = (long_beta - max_beta) / abs(short_beta) if short_beta != 0 else 1.0
        for t in list(weights.keys()):
            if weights[t] < 0:
                weights[t] *= scale
        logger.info("Beta-adjusted short book by %.2f", scale)

    return weights
