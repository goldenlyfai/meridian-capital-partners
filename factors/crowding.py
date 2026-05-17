"""L2: Crowding detection — factor return correlation analysis."""
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from data.db import get_conn
from data.market_data import get_returns

logger = logging.getLogger(__name__)

# Academic baseline pairwise correlations (momentum/value, momentum/quality, etc.)
BASELINES = {
    ("momentum", "value"): -0.30,
    ("momentum", "quality"): 0.10,
    ("value", "quality"): 0.05,
}
FLAG_THRESHOLD = 0.40


def compute_factor_returns(scored_df: pd.DataFrame, factor_cols: list[str], days: int = 60) -> pd.DataFrame:
    """
    Approximate daily factor returns as top-quintile minus bottom-quintile 1-day return.
    scored_df: DataFrame with [ticker] + factor columns, indexed by ticker.
    """
    conn = get_conn()
    tickers = scored_df.index.tolist()
    date_returns: dict[str, dict[str, float]] = {}

    for ticker in tickers:
        rets = get_returns(conn, ticker, days=days + 5)
        if rets.empty:
            continue
        for date, ret in rets.items():
            d = str(date)[:10]
            if d not in date_returns:
                date_returns[d] = {}
            date_returns[d][ticker] = ret

    conn.close()

    factor_return_series: dict[str, pd.Series] = {}
    for factor in factor_cols:
        if factor not in scored_df.columns:
            continue
        scores = scored_df[factor]
        dates_sorted = sorted(date_returns.keys())[-days:]
        daily_factor_rets = {}
        for d in dates_sorted:
            rets_d = pd.Series(date_returns.get(d, {}))
            if rets_d.empty:
                continue
            valid = scores.reindex(rets_d.index).dropna()
            if valid.empty:
                continue
            top = valid[valid >= valid.quantile(0.80)].index
            bot = valid[valid <= valid.quantile(0.20)].index
            top_ret = rets_d.reindex(top).mean()
            bot_ret = rets_d.reindex(bot).mean()
            if not np.isnan(top_ret) and not np.isnan(bot_ret):
                daily_factor_rets[d] = top_ret - bot_ret

        factor_return_series[factor] = pd.Series(daily_factor_rets)

    if not factor_return_series:
        return pd.DataFrame()

    return pd.DataFrame(factor_return_series).dropna(how="all")


def detect_crowding(scored_df: pd.DataFrame) -> list[dict]:
    """Return list of crowding alerts with factor pairs and deviations."""
    factor_cols = ["momentum", "value", "quality", "growth",
                   "estimate_revisions", "short_interest", "insider_activity", "institutional_flow"]

    existing = [c for c in factor_cols if c in scored_df.columns]
    if len(existing) < 2:
        return []

    factor_rets = compute_factor_returns(scored_df, existing)
    if factor_rets.empty or len(factor_rets) < 10:
        logger.warning("Not enough data for crowding detection")
        return []

    corr_matrix = factor_rets.corr()
    alerts = []
    for (f1, f2), baseline in BASELINES.items():
        if f1 not in corr_matrix.columns or f2 not in corr_matrix.columns:
            continue
        actual = corr_matrix.loc[f1, f2]
        deviation = abs(actual - baseline)
        if deviation > FLAG_THRESHOLD:
            alerts.append({
                "factor_pair": f"{f1}/{f2}",
                "actual_corr": round(actual, 3),
                "baseline_corr": baseline,
                "deviation": round(deviation, 3),
                "severity": "HIGH" if deviation > 0.60 else "MEDIUM",
            })
            logger.warning("CROWDING: %s/%s corr=%.2f (baseline %.2f, dev=%.2f)",
                           f1, f2, actual, baseline, deviation)

    return alerts
