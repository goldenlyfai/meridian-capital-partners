"""L5: Stress testing — 3 historical + 3 synthetic scenarios."""
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from data.db import get_conn

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "cache" / "stress"

HISTORICAL_SCENARIOS = [
    {
        "name": "2008 Financial Crisis",
        "start": "2008-09-01",
        "end": "2009-03-31",
    },
    {
        "name": "2020 COVID Crash",
        "start": "2020-02-01",
        "end": "2020-04-30",
    },
    {
        "name": "2022 Rate Hike Selloff",
        "start": "2022-01-01",
        "end": "2022-10-31",
    },
]


def _get_historical_returns(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    cache_path = CACHE_DIR / f"{start[:7]}_{end[:7]}.parquet"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if cache_path.exists():
        try:
            return pd.read_parquet(cache_path)
        except Exception:
            pass

    try:
        raw = yf.download(tickers, start=start, end=end, auto_adjust=True,
                          progress=False, group_by="ticker")
        if raw.empty:
            return pd.DataFrame()

        adj_close = pd.DataFrame()
        if isinstance(raw.columns, pd.MultiIndex):
            for t in tickers:
                if t in raw.columns.get_level_values(0):
                    adj_close[t] = raw[t]["Close"]
        else:
            adj_close = raw[["Close"]]

        rets = adj_close.pct_change().dropna(how="all")
        rets.to_parquet(cache_path)
        return rets
    except Exception as e:
        logger.warning("Stress test historical fetch: %s", e)
        return pd.DataFrame()


def run_stress_tests(weights: dict[str, float], aum: float) -> list[dict]:
    """Run all 6 scenarios and return estimated P&L."""
    tickers = list(weights.keys())
    results = []

    # --- Historical scenarios ---
    for scenario in HISTORICAL_SCENARIOS:
        rets = _get_historical_returns(tickers, scenario["start"], scenario["end"])

        total_ret = {}
        for t in tickers:
            if t in rets.columns:
                r = rets[t].dropna()
                total_ret[t] = float((1 + r).prod() - 1)
            else:
                total_ret[t] = 0.0

        port_ret = sum(weights.get(t, 0) * total_ret.get(t, 0) for t in tickers)
        long_ret = sum(weights.get(t, 0) * total_ret.get(t, 0)
                       for t in tickers if weights.get(t, 0) > 0)
        short_ret = sum(weights.get(t, 0) * total_ret.get(t, 0)
                        for t in tickers if weights.get(t, 0) < 0)

        results.append({
            "scenario": scenario["name"],
            "type": "historical",
            "period": f"{scenario['start']} to {scenario['end']}",
            "portfolio_return": round(port_ret, 4),
            "portfolio_pnl_usd": round(port_ret * aum, 0),
            "long_contribution": round(long_ret, 4),
            "short_contribution": round(short_ret, 4),
        })

    # --- Synthetic scenarios ---
    conn = get_conn()

    # Sector shock: -30% to most concentrated sector
    from portfolio.state import get_positions
    positions = get_positions()
    if not positions.empty:
        sector_counts = positions[positions["signal"] == "LONG"]["sector"].value_counts()
        top_sector = sector_counts.index[0] if not sector_counts.empty else "Information Technology"
        top_sector_tickers = positions[positions["sector"] == top_sector]["ticker"].tolist()
    else:
        top_sector = "Information Technology"
        top_sector_tickers = []

    sector_shock = sum(
        weights.get(t, 0) * (-0.30)
        for t in top_sector_tickers
    )
    results.append({
        "scenario": f"Sector Shock (-30% {top_sector})",
        "type": "synthetic",
        "period": "N/A",
        "portfolio_return": round(sector_shock, 4),
        "portfolio_pnl_usd": round(sector_shock * aum, 0),
        "long_contribution": round(sector_shock, 4),
        "short_contribution": 0.0,
    })

    # Momentum reversal: top quintile -20%, bottom +20%
    scored_path = Path(__file__).parent.parent / "output" / "scored_universe_latest.csv"
    if scored_path.exists():
        scored = pd.read_csv(scored_path, index_col="ticker")
        top_q = scored[scored["signal"] == "LONG"].index.tolist()
        bot_q = scored[scored["signal"] == "SHORT"].index.tolist()
        mom_rev = (
            sum(weights.get(t, 0) * (-0.20) for t in top_q)
            + sum(weights.get(t, 0) * 0.20 for t in bot_q)
        )
    else:
        mom_rev = sum(weights.get(t, 0) * (-0.20) for t in tickers if weights.get(t, 0) > 0)

    results.append({
        "scenario": "Momentum Reversal (long -20%, short +20%)",
        "type": "synthetic",
        "period": "N/A",
        "portfolio_return": round(mom_rev, 4),
        "portfolio_pnl_usd": round(mom_rev * aum, 0),
        "long_contribution": round(sum(weights.get(t, 0) * (-0.20) for t in tickers if weights.get(t, 0) > 0), 4),
        "short_contribution": round(sum(weights.get(t, 0) * 0.20 for t in tickers if weights.get(t, 0) < 0), 4),
    })

    # Short squeeze: all shorts +30%
    short_squeeze = sum(weights.get(t, 0) * 0.30 for t in tickers if weights.get(t, 0) < 0)
    results.append({
        "scenario": "Short Squeeze (all shorts +30%)",
        "type": "synthetic",
        "period": "N/A",
        "portfolio_return": round(short_squeeze, 4),
        "portfolio_pnl_usd": round(short_squeeze * aum, 0),
        "long_contribution": 0.0,
        "short_contribution": round(short_squeeze, 4),
    })

    conn.close()
    return results
