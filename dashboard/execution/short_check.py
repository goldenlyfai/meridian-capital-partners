"""L6: Short availability check via Alpaca."""
import logging
from datetime import datetime, timedelta

from data.db import get_conn

logger = logging.getLogger(__name__)


def check_shortable(ticker: str) -> bool:
    """Return True if ticker is shortable on Alpaca."""
    conn = get_conn()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS short_availability
           (ticker TEXT PRIMARY KEY, shortable INTEGER, easy_to_borrow INTEGER, checked_at TEXT)"""
    )
    # Check cache (7 days)
    row = conn.execute(
        "SELECT shortable, easy_to_borrow, checked_at FROM short_availability WHERE ticker=?",
        (ticker,),
    ).fetchone()

    if row:
        checked = datetime.fromisoformat(row[2])
        if (datetime.utcnow() - checked) < timedelta(days=7):
            conn.close()
            return bool(row[0]) and bool(row[1])

    try:
        from execution.broker import get_trading_client
        client = get_trading_client()
        asset = client.get_asset(ticker)
        shortable = bool(getattr(asset, "shortable", False))
        etb = bool(getattr(asset, "easy_to_borrow", False))

        conn.execute(
            """INSERT OR REPLACE INTO short_availability
               (ticker, shortable, easy_to_borrow, checked_at) VALUES (?,?,?,?)""",
            (ticker, int(shortable), int(etb), datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()

        if not shortable or not etb:
            logger.warning("Short NOT available: %s (shortable=%s, ETB=%s)",
                           ticker, shortable, etb)
        return shortable and etb

    except Exception as e:
        logger.warning("Short check %s: %s — assuming shortable", ticker, e)
        conn.close()
        return True
