"""Shared SQLite connection and table initialisation."""
import sqlite3
import os
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())

# Allow Railway volume override via env var
_db_env = os.getenv("MERIDIAN_DB_PATH")
DB_PATH = Path(_db_env) if _db_env else ROOT / _cfg["database"]["path"]


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
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
    """)

    conn.commit()
    conn.close()
