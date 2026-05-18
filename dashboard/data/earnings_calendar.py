"""L1-8: Earnings calendar — upcoming dates for universe tickers."""
import logging
import time
from datetime import datetime

import yfinance as yf

from .db import get_conn

logger = logging.getLogger(__name__)

BATCH_SIZE = 25


def refresh_earnings_calendar(tickers: list[str]) -> dict:
    conn = get_conn()
    summary = {"updated": 0, "errors": []}
    now_iso = datetime.utcnow().isoformat()

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        for ticker in batch:
            try:
                yt = yf.Ticker(ticker)
                earnings_dates = []

                # Try get_earnings_dates() first (newer yfinance, returns DataFrame)
                try:
                    df = yt.get_earnings_dates(limit=4)
                    if df is not None and not df.empty:
                        from datetime import datetime as dt
                        today_str = dt.utcnow().strftime("%Y-%m-%d")
                        future = [str(d)[:10] for d in df.index if str(d)[:10] >= today_str]
                        earnings_dates = future
                except Exception:
                    pass

                # Fallback: .calendar dict format
                if not earnings_dates:
                    cal = yt.calendar
                    if isinstance(cal, dict):
                        raw = cal.get("Earnings Date", cal.get("earningsDate", []))
                        if isinstance(raw, list):
                            earnings_dates = [str(d)[:10] for d in raw if d]
                        elif raw:
                            earnings_dates = [str(raw)[:10]]
                    elif hasattr(cal, "empty") and not cal.empty and "Earnings Date" in cal.index:
                        val = cal.loc["Earnings Date"]
                        if hasattr(val, "__iter__") and not isinstance(val, str):
                            earnings_dates = [str(v)[:10] for v in val if v]
                        else:
                            earnings_dates = [str(val)[:10]]

                for d in earnings_dates:
                    conn.execute(
                        """INSERT OR REPLACE INTO earnings_calendar
                           (ticker, earnings_date, fetched_at) VALUES (?,?,?)""",
                        (ticker, d, now_iso),
                    )
                if earnings_dates:
                    summary["updated"] += 1

            except Exception as e:
                logger.debug("Earnings calendar %s: %s", ticker, e)
                summary["errors"].append(f"{ticker}: {e}")

        conn.commit()
        time.sleep(1.0)

    conn.close()
    return summary


def get_upcoming_earnings(conn, days: int = 7) -> list[dict]:
    from datetime import timedelta
    today = datetime.utcnow().strftime("%Y-%m-%d")
    end = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT ticker, earnings_date FROM earnings_calendar
           WHERE earnings_date >= ? AND earnings_date <= ?
           ORDER BY earnings_date""",
        (today, end),
    ).fetchall()
    return [{"ticker": r[0], "earnings_date": r[1]} for r in rows]


def has_earnings_soon(conn, ticker: str, days: int = 5) -> bool:
    upcoming = get_upcoming_earnings(conn, days=days)
    return any(u["ticker"] == ticker for u in upcoming)
