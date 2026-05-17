"""L1-6: Short interest snapshots via yfinance."""
import logging
import time
from datetime import datetime

import yfinance as yf

from .db import get_conn

logger = logging.getLogger(__name__)

BATCH_SIZE = 25


def refresh_short_interest(tickers: list[str]) -> dict:
    conn = get_conn()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    summary = {"updated": 0, "errors": []}

    # Batch in groups to avoid hammering yfinance
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        for ticker in batch:
            try:
                info = yf.Ticker(ticker).fast_info
                shares_short = getattr(info, "shares_short", None)
                # fast_info doesn't have short_ratio; fall back to .info for a subset
                short_ratio = None
                short_pct = None

                # Try to get more detail from .info (slower, only when fast_info gives nothing)
                if shares_short is None:
                    full = yf.Ticker(ticker).info or {}
                    shares_short = full.get("sharesShort")
                    short_ratio = full.get("shortRatio")
                    short_pct = full.get("shortPercentOfFloat")

                if shares_short is None and short_ratio is None:
                    continue

                conn.execute(
                    """INSERT OR REPLACE INTO short_interest
                       (ticker, date, shares_short, short_ratio, short_percent_float, fetched_at)
                       VALUES (?,?,?,?,?,?)""",
                    (ticker, today, shares_short, short_ratio, short_pct,
                     datetime.utcnow().isoformat()),
                )
                summary["updated"] += 1
            except Exception as e:
                logger.debug("Short interest %s: %s", ticker, e)
                summary["errors"].append(f"{ticker}: {e}")

        conn.commit()
        time.sleep(1.0)  # throttle between batches

    conn.close()
    return summary


def get_short_interest(conn, ticker: str) -> dict:
    row = conn.execute(
        """SELECT shares_short, short_ratio, short_percent_float, date
           FROM short_interest WHERE ticker=? ORDER BY date DESC LIMIT 1""",
        (ticker,),
    ).fetchone()
    if not row:
        return {}
    return {
        "shares_short": row[0],
        "short_ratio": row[1],
        "short_percent_float": row[2],
        "date": row[3],
    }


def get_short_interest_change(conn, ticker: str) -> float | None:
    """Return % change in short interest vs prior snapshot."""
    rows = conn.execute(
        """SELECT short_percent_float FROM short_interest
           WHERE ticker=? ORDER BY date DESC LIMIT 2""",
        (ticker,),
    ).fetchall()
    if len(rows) < 2:
        return None
    latest, prior = rows[0][0], rows[1][0]
    if prior and prior != 0:
        return (latest - prior) / prior
    return None
