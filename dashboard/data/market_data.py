"""L1-2: Daily OHLCV market data via yfinance (with Polygon fallback)."""
import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from .db import get_conn
from .providers import get_providers

logger = logging.getLogger(__name__)

LOOKBACK_YEARS = 3
BATCH_SIZE = 50


def _latest_date(conn, ticker: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(date) FROM daily_prices WHERE ticker=?", (ticker,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _fetch_yfinance(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    raw = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    return raw


def _upsert_prices(conn, ticker: str, df: pd.DataFrame):
    if df.empty:
        return 0
    rows = []
    for date_idx, row in df.iterrows():
        date_str = str(date_idx)[:10]
        rows.append((
            ticker, date_str,
            float(row.get("Open", 0) or 0),
            float(row.get("High", 0) or 0),
            float(row.get("Low", 0) or 0),
            float(row.get("Close", 0) or 0),
            float(row.get("Volume", 0) or 0),
            float(row.get("Close", 0) or 0),
        ))
    if getattr(conn, "_pg", False):
        # Postgres: bulk insert via execute_values (single round-trip for all rows)
        from psycopg2.extras import execute_values
        cur = conn._conn.cursor()
        execute_values(
            cur,
            """INSERT INTO daily_prices
               (ticker, date, open, high, low, close, volume, adj_close)
               VALUES %s
               ON CONFLICT (ticker, date) DO UPDATE SET
               open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
               close=EXCLUDED.close, volume=EXCLUDED.volume, adj_close=EXCLUDED.adj_close""",
            rows,
            page_size=500,
        )
    else:
        conn.executemany(
            """INSERT OR REPLACE INTO daily_prices
               (ticker, date, open, high, low, close, volume, adj_close)
               VALUES (?,?,?,?,?,?,?,?)""",
            rows,
        )
    return len(rows)


def refresh_prices(tickers: list[str], lookback_years: int = LOOKBACK_YEARS) -> dict:
    providers = get_providers()
    conn = get_conn()
    summary = {"tickers_updated": 0, "bars_added": 0, "errors": []}
    cutoff = (datetime.utcnow() - timedelta(days=365 * lookback_years)).strftime("%Y-%m-%d")
    today = datetime.utcnow().strftime("%Y-%m-%d")

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        starts: dict[str, str] = {}
        for t in batch:
            latest = _latest_date(conn, t)
            starts[t] = (
                (datetime.fromisoformat(latest) + timedelta(days=1)).strftime("%Y-%m-%d")
                if latest else cutoff
            )

        global_start = min(starts.values())
        if global_start >= today:
            continue

        try:
            if len(batch) == 1:
                raw = yf.download(
                    batch[0], start=global_start, end=today,
                    auto_adjust=True, progress=False,
                )
                if not raw.empty:
                    n = _upsert_prices(conn, batch[0], raw)
                    summary["bars_added"] += n
                    if n:
                        summary["tickers_updated"] += 1
            else:
                raw = _fetch_yfinance(batch, global_start, today)
                if raw.empty:
                    continue
                for t in batch:
                    try:
                        if isinstance(raw.columns, pd.MultiIndex):
                            t_df = raw[t] if t in raw.columns.get_level_values(0) else pd.DataFrame()
                        else:
                            t_df = raw
                        if not t_df.empty:
                            t_df = t_df[t_df.index >= starts[t]]
                            n = _upsert_prices(conn, t, t_df)
                            summary["bars_added"] += n
                            if n:
                                summary["tickers_updated"] += 1
                    except Exception as e:
                        summary["errors"].append(f"{t}: {e}")

            conn.commit()
            logger.info("Batch %d/%d done", i // BATCH_SIZE + 1, -(-len(tickers) // BATCH_SIZE))
            time.sleep(0.5)

        except Exception as e:
            logger.error("Batch error: %s", e)
            summary["errors"].append(str(e))

    conn.close()
    return summary


def get_prices(conn, ticker: str, days: int = 252) -> pd.DataFrame:
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql(
        "SELECT date, open, high, low, close, volume, adj_close FROM daily_prices "
        "WHERE ticker=? AND date>=? ORDER BY date",
        conn, params=(ticker, cutoff),
    )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
    return df


def get_returns(conn, ticker: str, days: int = 252) -> pd.Series:
    df = get_prices(conn, ticker, days + 5)
    if df.empty:
        return pd.Series(dtype=float)
    return df["adj_close"].pct_change().dropna()


def get_adv(conn, ticker: str, window: int = 20) -> float:
    """Average daily dollar volume over last `window` days."""
    df = get_prices(conn, ticker, days=window + 5)
    if df.empty or len(df) < 2:
        return 0.0
    recent = df.tail(window)
    return float((recent["close"] * recent["volume"]).mean())
