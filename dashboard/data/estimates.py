"""L1-7: Analyst estimates — forward EPS, price target snapshots."""
import logging
import time
from datetime import datetime

import yfinance as yf

from .db import get_conn

logger = logging.getLogger(__name__)

BATCH_SIZE = 25


def refresh_estimates(tickers: list[str]) -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    summary = {"updated": 0, "errors": []}

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        conn = get_conn()
        try:
            for ticker in batch:
                time.sleep(0.3)
                try:
                    info = yf.Ticker(ticker).info or {}
                    forward_eps = info.get("forwardEps")
                    price_target = info.get("targetMeanPrice")
                    num_analysts = info.get("numberOfAnalystOpinions")

                    if forward_eps is None and price_target is None:
                        continue

                    conn.execute(
                        """INSERT OR REPLACE INTO analyst_estimates
                           (ticker, date, forward_eps, price_target, num_analysts, fetched_at)
                           VALUES (?,?,?,?,?,?)""",
                        (ticker, today, forward_eps, price_target, num_analysts,
                         datetime.utcnow().isoformat()),
                    )
                    summary["updated"] += 1
                except Exception as e:
                    logger.debug("Estimates %s: %s", ticker, e)
                    summary["errors"].append(f"{ticker}: {e}")

            conn.commit()
        except Exception as e:
            logger.warning("Estimates batch %d commit failed: %s", i // BATCH_SIZE, e)
        finally:
            conn.close()
        time.sleep(1.0)

    return summary


def get_estimate_revisions(conn, ticker: str) -> dict:
    """Return 30/60/90-day deltas in forward EPS."""
    rows = conn.execute(
        """SELECT date, forward_eps FROM analyst_estimates
           WHERE ticker=? ORDER BY date DESC LIMIT 100""",
        (ticker,),
    ).fetchall()

    if not rows or len(rows) < 2:
        return {"rev_30d": None, "rev_60d": None, "rev_90d": None}

    from datetime import timedelta
    import pandas as pd

    df = pd.DataFrame(rows, columns=["date", "forward_eps"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    latest_date = df.index[-1]
    latest_eps = df["forward_eps"].iloc[-1]

    def delta_at(days):
        target = latest_date - timedelta(days=days)
        past = df[df.index <= target]
        if past.empty:
            return None
        past_eps = past["forward_eps"].iloc[-1]
        if past_eps and past_eps != 0:
            return (latest_eps - past_eps) / abs(past_eps)
        return None

    return {
        "rev_30d": delta_at(30),
        "rev_60d": delta_at(60),
        "rev_90d": delta_at(90),
    }
