"""
Unified database connection — SQLite for local dev, Neon Postgres on Vercel.

Detection:
  DATABASE_URL set  → Postgres (Neon)
  MERIDIAN_DB_PATH  → custom SQLite path (Railway volume)
  default           → cache/meridian.db (local)

SQL compatibility:
  - Translates ? → %s for Postgres
  - INSERT OR REPLACE → INSERT ... ON CONFLICT (...) DO UPDATE SET ...
  - INSERT OR IGNORE  → INSERT ... ON CONFLICT DO NOTHING
  - CREATE TABLE AUTOINCREMENT → SERIAL PRIMARY KEY
"""
import os
import re
import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())

DATABASE_URL = os.getenv("DATABASE_URL")
_db_env = os.getenv("MERIDIAN_DB_PATH")
DB_PATH = Path(_db_env) if _db_env else ROOT / _cfg["database"]["path"]
USE_POSTGRES = bool(DATABASE_URL)

# Primary key columns per table — needed to generate ON CONFLICT targets
_TABLE_PK: dict[str, list[str]] = {
    "universe":               ["ticker"],
    "daily_prices":           ["ticker", "date"],
    "fundamentals":           ["ticker", "period", "period_type"],
    "institutional_holdings": ["fund_name", "ticker", "report_date"],
    "short_interest":         ["ticker", "date"],
    "analyst_estimates":      ["ticker", "date"],
    "earnings_calendar":      ["ticker", "earnings_date"],
    "earnings_transcripts":   ["ticker", "quarter"],
    "portfolio_positions":    ["ticker"],
    "position_approvals":     ["ticker"],
    "analysis_results":       ["analyzer", "ticker", "artifact_id"],
    "short_availability":     ["ticker"],
    "veto_log":               [],   # append-only
    "fills":                  [],   # append-only
    "portfolio_history":      [],   # append-only
}

_RE_REPLACE = re.compile(
    r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)
_RE_IGNORE = re.compile(
    r"INSERT\s+OR\s+IGNORE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)
_RE_AUTOINCREMENT = re.compile(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", re.IGNORECASE)
_RE_INTEGER = re.compile(r"\bINTEGER\b(?!\s+PRIMARY)", re.IGNORECASE)


def _pg_upsert(m: re.Match) -> str:
    table = m.group(1)
    cols_raw = m.group(2)
    vals = m.group(3)
    cols = [c.strip() for c in cols_raw.split(",")]
    pk = _TABLE_PK.get(table, [cols[0]])
    if not pk:
        return f"INSERT INTO {table} ({cols_raw}) VALUES ({vals})"
    non_pk = [c for c in cols if c not in pk] or [cols[-1]]
    update = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_pk)
    return (
        f"INSERT INTO {table} ({cols_raw}) VALUES ({vals})"
        f" ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {update}"
    )


def _pg_ignore(m: re.Match) -> str:
    table, cols_raw, vals = m.group(1), m.group(2), m.group(3)
    return f"INSERT INTO {table} ({cols_raw}) VALUES ({vals}) ON CONFLICT DO NOTHING"


def _adapt(sql: str) -> str:
    """Translate SQLite SQL to Postgres-compatible SQL."""
    sql = sql.replace("?", "%s")
    sql = _RE_REPLACE.sub(_pg_upsert, sql)
    sql = _RE_IGNORE.sub(_pg_ignore, sql)
    return sql


def _adapt_create(sql: str) -> str:
    sql = _RE_AUTOINCREMENT.sub("SERIAL PRIMARY KEY", sql)
    sql = _RE_INTEGER.sub("BIGINT", sql)
    return sql


class _Cursor:
    """Wraps psycopg2 cursor to expose fetchone/fetchall like sqlite3."""
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur.fetchall())


class _AdaptedCursor:
    """
    Psycopg2 cursor wrapper that translates ? placeholders → %s.
    Returned by Connection.cursor() so pandas.read_sql works transparently.
    """
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql: str, params=None):
        self._cur.execute(_adapt(sql), params)
        return self

    def executemany(self, sql: str, seq):
        self._cur.executemany(_adapt(sql), seq)

    def fetchone(self):   return self._cur.fetchone()
    def fetchall(self):   return self._cur.fetchall()
    def fetchmany(self, size=None): return self._cur.fetchmany(size)
    def __iter__(self):   return iter(self._cur)
    def close(self):      self._cur.close()

    @property
    def description(self): return self._cur.description
    @property
    def rowcount(self):    return self._cur.rowcount


class Connection:
    """Unified SQLite / Postgres connection with automatic SQL translation."""

    def __init__(self):
        if USE_POSTGRES:
            import psycopg2
            self._conn = psycopg2.connect(DATABASE_URL)
            self._pg = True
        else:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._pg = False

    # ── core execute ─────────────────────────────────────────────────────────

    def execute(self, sql: str, params=()):
        if self._pg:
            cur = self._conn.cursor()
            cur.execute(_adapt(sql), params or ())
            return _Cursor(cur)
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params_list):
        if self._pg:
            cur = self._conn.cursor()
            cur.executemany(_adapt(sql), params_list)
            return _Cursor(cur)
        return self._conn.executemany(sql, params_list)

    def executescript(self, script: str):
        """Run a multi-statement DDL script."""
        if self._pg:
            cur = self._conn.cursor()
            for raw in script.split(";"):
                stmt = raw.strip()
                if not stmt:
                    continue
                stmt = _adapt_create(stmt)
                stmt = _adapt(stmt)
                try:
                    cur.execute(stmt)
                except Exception:
                    pass  # table / index already exists
        else:
            self._conn.executescript(script)

    # ── pandas compatibility ──────────────────────────────────────────────────

    def cursor(self):
        """Return an adapted cursor — translates ? placeholders for pandas.read_sql."""
        if self._pg:
            return _AdaptedCursor(self._conn.cursor())
        return self._conn.cursor()

    # ── transaction ──────────────────────────────────────────────────────────

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ── delegate everything else to the underlying connection ────────────────

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def get_conn() -> Connection:
    return Connection()


def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS universe (
        ticker TEXT PRIMARY KEY,
        company_name TEXT,
        sector TEXT,
        sub_industry TEXT,
        is_benchmark INTEGER DEFAULT 0,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS daily_prices (
        ticker TEXT NOT NULL,
        date TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        adj_close REAL,
        PRIMARY KEY (ticker, date)
    );

    CREATE TABLE IF NOT EXISTS fundamentals (
        ticker TEXT NOT NULL,
        period TEXT NOT NULL,
        period_type TEXT NOT NULL,
        roe REAL, roa REAL, gross_margin REAL, operating_margin REAL, net_margin REAL,
        revenue_growth_yoy REAL, revenue_growth_qoq REAL,
        earnings_growth_yoy REAL, earnings_growth_qoq REAL,
        debt_to_equity REAL, fcf_yield REAL, current_ratio REAL,
        ar_to_revenue REAL, cfo_to_ni REAL, accruals_ratio REAL,
        retained_earnings REAL, working_capital REAL, total_liabilities REAL,
        ebit REAL, rd_expense REAL, shares_outstanding REAL,
        dividends_paid REAL, buybacks REAL, asset_turnover REAL,
        revenue REAL, net_income REAL, cfo REAL, total_assets REAL,
        market_cap REAL, book_value REAL, ev REAL, ebitda REAL,
        forward_pe REAL, forward_eps REAL, price_to_book REAL,
        updated_at TEXT,
        PRIMARY KEY (ticker, period, period_type)
    );

    CREATE TABLE IF NOT EXISTS insider_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        insider_name TEXT,
        insider_title TEXT,
        transaction_type TEXT,
        transaction_code TEXT,
        shares REAL,
        price REAL,
        amount REAL,
        date TEXT,
        ownership_type TEXT,
        is_ceo_cfo INTEGER DEFAULT 0,
        filing_url TEXT,
        fetched_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_insider_ticker_date ON insider_transactions(ticker, date);

    CREATE TABLE IF NOT EXISTS institutional_holdings (
        fund_name TEXT NOT NULL,
        ticker TEXT NOT NULL,
        shares_held REAL,
        market_value REAL,
        report_date TEXT NOT NULL,
        prior_shares REAL,
        net_change REAL,
        fetched_at TEXT,
        PRIMARY KEY (fund_name, ticker, report_date)
    );

    CREATE TABLE IF NOT EXISTS short_interest (
        ticker TEXT NOT NULL,
        date TEXT NOT NULL,
        shares_short REAL,
        short_ratio REAL,
        short_percent_float REAL,
        fetched_at TEXT,
        PRIMARY KEY (ticker, date)
    );

    CREATE TABLE IF NOT EXISTS analyst_estimates (
        ticker TEXT NOT NULL,
        date TEXT NOT NULL,
        forward_eps REAL,
        price_target REAL,
        num_analysts INTEGER,
        fetched_at TEXT,
        PRIMARY KEY (ticker, date)
    );

    CREATE TABLE IF NOT EXISTS earnings_calendar (
        ticker TEXT NOT NULL,
        earnings_date TEXT NOT NULL,
        fetched_at TEXT,
        PRIMARY KEY (ticker, earnings_date)
    );

    CREATE TABLE IF NOT EXISTS earnings_transcripts (
        ticker TEXT NOT NULL,
        quarter TEXT NOT NULL,
        year INTEGER,
        transcript TEXT,
        fetched_at TEXT,
        PRIMARY KEY (ticker, quarter)
    );

    CREATE TABLE IF NOT EXISTS analysis_results (
        analyzer TEXT NOT NULL,
        ticker TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        result_json TEXT,
        created_at TEXT,
        PRIMARY KEY (analyzer, ticker, artifact_id)
    );

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
