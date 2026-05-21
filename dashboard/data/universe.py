"""L1-1: Universe management — S&P 500 + benchmarks."""
import logging
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .db import get_conn

logger = logging.getLogger(__name__)

BENCHMARK_TICKERS = [
    "SPY", "QQQ", "IWM", "DIA",
    "XLK", "XLF", "XLV", "XLE", "XLI", "XLC", "XLY", "XLP", "XLB", "XLRE", "XLU",
    "^VIX", "TLT", "HYG",
]

SECTOR_ETF_MAP = {
    "Information Technology": "XLK",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}


def _scrape_sp500() -> pd.DataFrame:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", {"id": "constituents"})
    rows = []
    for tr in table.find_all("tr")[1:]:
        cols = tr.find_all("td")
        if len(cols) >= 4:
            ticker = cols[0].text.strip().replace(".", "-")
            company = cols[1].text.strip()
            sector = cols[2].text.strip()
            sub = cols[3].text.strip()
            rows.append({"ticker": ticker, "company_name": company,
                         "sector": sector, "sub_industry": sub})
    return pd.DataFrame(rows)


def _should_refresh(conn: sqlite3.Connection, refresh_days: int) -> bool:
    row = conn.execute(
        "SELECT updated_at FROM universe ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        return True
    last = datetime.fromisoformat(row[0])
    return (datetime.utcnow() - last) > timedelta(days=refresh_days)


def refresh_universe(refresh_days: int = 7) -> int:
    conn = get_conn()
    try:
        if not _should_refresh(conn, refresh_days):
            count = conn.execute(
                "SELECT COUNT(*) FROM universe WHERE is_benchmark=0"
            ).fetchone()[0]
            logger.info("Universe cache fresh — %d tickers", count)
            return count

        logger.info("Scraping S&P 500 from Wikipedia…")
        df = _scrape_sp500()
        now = datetime.utcnow().isoformat()

        conn.execute("DELETE FROM universe WHERE is_benchmark=0 AND (is_custom=0 OR is_custom IS NULL)")
        for _, row in df.iterrows():
            conn.execute(
                """INSERT OR REPLACE INTO universe
                   (ticker, company_name, sector, sub_industry, is_benchmark, updated_at)
                   VALUES (?,?,?,?,0,?)""",
                (row["ticker"], row["company_name"], row["sector"], row["sub_industry"], now),
            )

        for t in BENCHMARK_TICKERS:
            conn.execute(
                """INSERT OR REPLACE INTO universe
                   (ticker, company_name, sector, sub_industry, is_benchmark, updated_at)
                   VALUES (?,?,?,?,1,?)""",
                (t, t, "Benchmark", "Benchmark", now),
            )

        conn.commit()
        logger.info("Universe refreshed: %d stocks + %d benchmarks", len(df), len(BENCHMARK_TICKERS))
        return len(df)
    finally:
        conn.close()


def get_sp500_tickers(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT ticker FROM universe WHERE is_benchmark=0 ORDER BY ticker"
    ).fetchall()
    return [r[0] for r in rows]


def get_all_tickers(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT ticker FROM universe ORDER BY ticker").fetchall()
    return [r[0] for r in rows]


def get_ticker_sector(conn: sqlite3.Connection, ticker: str) -> str | None:
    row = conn.execute(
        "SELECT sector FROM universe WHERE ticker=?", (ticker,)
    ).fetchone()
    return row[0] if row else None


def get_sector_tickers(conn: sqlite3.Connection, sector: str) -> list[str]:
    rows = conn.execute(
        "SELECT ticker FROM universe WHERE sector=? AND is_benchmark=0", (sector,)
    ).fetchall()
    return [r[0] for r in rows]


def get_universe_df(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM universe", conn)
