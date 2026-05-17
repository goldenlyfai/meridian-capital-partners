"""L4: Portfolio state — SQLite positions + history."""
import logging
from datetime import datetime

import pandas as pd

from data.db import get_conn

logger = logging.getLogger(__name__)


def init_portfolio_tables():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS portfolio_positions (
        ticker TEXT PRIMARY KEY,
        shares REAL,
        entry_price REAL,
        entry_date TEXT,
        current_price REAL,
        unrealized_pnl REAL,
        sector TEXT,
        signal TEXT,
        composite_score REAL,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS portfolio_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        ticker TEXT,
        action TEXT,
        shares REAL,
        price REAL,
        pnl REAL,
        reason TEXT,
        logged_at TEXT
    );

    CREATE TABLE IF NOT EXISTS position_approvals (
        ticker TEXT PRIMARY KEY,
        action TEXT,
        status TEXT,
        reviewed_at TEXT,
        reviewer TEXT
    );
    """)
    conn.commit()
    conn.close()


def get_positions() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM portfolio_positions", conn)
    conn.close()
    return df


def get_position(ticker: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM portfolio_positions WHERE ticker=?", (ticker,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    cols = ["ticker", "shares", "entry_price", "entry_date", "current_price",
            "unrealized_pnl", "sector", "signal", "composite_score", "updated_at"]
    return dict(zip(cols, row))


def upsert_position(ticker: str, shares: float, price: float, sector: str,
                    signal: str, composite_score: float, entry_date: str | None = None):
    conn = get_conn()
    existing = conn.execute(
        "SELECT entry_price, entry_date FROM portfolio_positions WHERE ticker=?", (ticker,)
    ).fetchone()

    ep = existing[0] if existing else price
    ed = existing[1] if existing else (entry_date or datetime.utcnow().strftime("%Y-%m-%d"))
    upnl = (price - ep) * shares if shares > 0 else (ep - price) * abs(shares)

    conn.execute(
        """INSERT OR REPLACE INTO portfolio_positions
           (ticker, shares, entry_price, entry_date, current_price, unrealized_pnl,
            sector, signal, composite_score, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (ticker, shares, ep, ed, price, upnl, sector, signal, composite_score,
         datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def close_position(ticker: str, fill_price: float, reason: str = ""):
    conn = get_conn()
    pos = conn.execute(
        "SELECT shares, entry_price FROM portfolio_positions WHERE ticker=?", (ticker,)
    ).fetchone()
    if pos:
        shares, ep = pos
        pnl = (fill_price - ep) * shares
        conn.execute(
            """INSERT INTO portfolio_history
               (date, ticker, action, shares, price, pnl, reason, logged_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (datetime.utcnow().strftime("%Y-%m-%d"), ticker, "CLOSE",
             shares, fill_price, pnl, reason, datetime.utcnow().isoformat()),
        )
        conn.execute("DELETE FROM portfolio_positions WHERE ticker=?", (ticker,))
        conn.commit()
    conn.close()


def update_current_prices():
    """Refresh unrealized P&L using latest prices."""
    conn = get_conn()
    positions = conn.execute(
        "SELECT ticker, shares, entry_price FROM portfolio_positions"
    ).fetchall()

    for ticker, shares, ep in positions:
        row = conn.execute(
            "SELECT close FROM daily_prices WHERE ticker=? ORDER BY date DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if row:
            cur = float(row[0])
            upnl = (cur - ep) * shares
            conn.execute(
                "UPDATE portfolio_positions SET current_price=?, unrealized_pnl=?, updated_at=? WHERE ticker=?",
                (cur, upnl, datetime.utcnow().isoformat(), ticker),
            )

    conn.commit()
    conn.close()
