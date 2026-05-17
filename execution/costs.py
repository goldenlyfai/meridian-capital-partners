"""L6: Slippage tracker."""
import logging
from datetime import datetime, timedelta

import pandas as pd

from data.db import get_conn

logger = logging.getLogger(__name__)


def record_fill(
    ticker: str,
    side: str,
    shares: float,
    signal_price: float,
    fill_price: float,
    order_id: str,
):
    """Record a fill and compute slippage."""
    conn = get_conn()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS fills
           (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, side TEXT,
            shares REAL, signal_price REAL, fill_price REAL, slippage_bps REAL,
            order_id TEXT, filled_at TEXT)"""
    )
    slippage_bps = (fill_price - signal_price) / signal_price * 10_000
    if side in ("SELL", "SHORT"):
        slippage_bps = -slippage_bps  # for sells, lower is worse

    conn.execute(
        """INSERT INTO fills
           (ticker, side, shares, signal_price, fill_price, slippage_bps, order_id, filled_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (ticker, side, shares, signal_price, fill_price, slippage_bps,
         order_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    logger.info("Fill: %s %s %d @ $%.2f (signal $%.2f, slip %.1fbps)",
                side, ticker, shares, fill_price, signal_price, slippage_bps)


def get_slippage_stats(days: int = 30) -> dict:
    conn = get_conn()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    try:
        df = pd.read_sql(
            "SELECT * FROM fills WHERE filled_at >= ?", conn, params=(cutoff,)
        )
    except Exception:
        conn.close()
        return {}
    conn.close()

    if df.empty:
        return {"count": 0}

    worst_5 = df.nlargest(5, "slippage_bps")[
        ["ticker", "side", "shares", "slippage_bps", "filled_at"]
    ].to_dict("records")

    return {
        "count": len(df),
        "avg_slippage_bps": round(float(df["slippage_bps"].mean()), 2),
        "median_slippage_bps": round(float(df["slippage_bps"].median()), 2),
        "p95_slippage_bps": round(float(df["slippage_bps"].quantile(0.95)), 2),
        "total_dollar_cost": round(float(
            (df["slippage_bps"] / 10_000 * df["fill_price"] * df["shares"]).sum()
        ), 2),
        "worst_5": worst_5,
    }
