"""L1-3: Quarterly + annual fundamentals with 24 derived ratios."""
import logging
from datetime import datetime

import pandas as pd
import yfinance as yf

from .db import get_conn

logger = logging.getLogger(__name__)


def _safe(val, default=None):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except Exception:
        return default


def _calc_ratios(info: dict, income: pd.DataFrame, balance: pd.DataFrame,
                 cashflow: pd.DataFrame, period: str, period_type: str) -> dict:
    """Derive the 24 fundamental ratios for a single period."""
    r: dict = {"period": period, "period_type": period_type}

    def get(df, *keys):
        for k in keys:
            if k in df.index:
                col = df.columns[0] if not df.empty else None
                if col is not None:
                    return _safe(df.loc[k, col])
        return None

    revenue = get(income, "Total Revenue", "TotalRevenue")
    ni = get(income, "Net Income", "NetIncome")
    gross_profit = get(income, "Gross Profit", "GrossProfit")
    ebit = get(income, "EBIT", "Operating Income", "OperatingIncome")
    rd = get(income, "Research Development", "ResearchAndDevelopment", "RAndD")
    shares = get(income, "Basic Average Shares", "BasicAverageShares") or _safe(info.get("sharesOutstanding"))

    total_assets = get(balance, "Total Assets", "TotalAssets")
    total_liabilities = get(balance, "Total Liabilities Net Minority Interest", "TotalLiabilitiesNetMinorityInterest")
    total_equity = get(balance, "Stockholders Equity", "StockholdersEquity")
    current_assets = get(balance, "Current Assets", "CurrentAssets")
    current_liabilities = get(balance, "Current Liabilities", "CurrentLiabilities")
    ar = get(balance, "Accounts Receivable", "AccountsReceivable")
    retained = get(balance, "Retained Earnings", "RetainedEarnings")
    total_debt = get(balance, "Total Debt", "TotalDebt", "Long Term Debt", "LongTermDebt") or 0

    cfo = get(cashflow, "Operating Cash Flow", "OperatingCashFlow")
    capex = get(cashflow, "Capital Expenditure", "CapitalExpenditure") or 0
    dividends = get(cashflow, "Common Stock Dividends Paid", "DividendsPaid") or 0
    buybacks = get(cashflow, "Repurchase Of Capital Stock", "RepurchaseOfCapitalStock") or 0

    mkt_cap = _safe(info.get("marketCap"))
    book_val = _safe(info.get("bookValue")) or (total_equity / shares if total_equity and shares else None)
    forward_pe = _safe(info.get("forwardPE"))
    forward_eps = _safe(info.get("forwardEps"))

    fcf = (cfo + capex) if (cfo is not None and capex is not None) else None
    ev = _safe(info.get("enterpriseValue"))
    ebitda = _safe(info.get("ebitda"))

    wc = (current_assets - current_liabilities) if (current_assets and current_liabilities) else None

    r["revenue"] = revenue
    r["net_income"] = ni
    r["cfo"] = cfo
    r["total_assets"] = total_assets
    r["market_cap"] = mkt_cap
    r["book_value"] = book_val
    r["ev"] = ev
    r["ebitda"] = ebitda
    r["forward_pe"] = forward_pe
    r["forward_eps"] = forward_eps
    r["ebit"] = ebit
    r["rd_expense"] = rd
    r["shares_outstanding"] = shares
    r["dividends_paid"] = dividends
    r["buybacks"] = buybacks
    r["total_liabilities"] = total_liabilities
    r["working_capital"] = wc
    r["retained_earnings"] = retained

    r["roe"] = (ni / total_equity) if (ni and total_equity) else None
    r["roa"] = (ni / total_assets) if (ni and total_assets) else None
    r["gross_margin"] = (gross_profit / revenue) if (gross_profit and revenue) else None
    r["operating_margin"] = (ebit / revenue) if (ebit and revenue) else None
    r["net_margin"] = (ni / revenue) if (ni and revenue) else None
    r["debt_to_equity"] = (total_debt / total_equity) if (total_equity and total_equity != 0) else None
    r["fcf_yield"] = (fcf / mkt_cap) if (fcf and mkt_cap) else None
    r["current_ratio"] = (current_assets / current_liabilities) if (current_assets and current_liabilities and current_liabilities != 0) else None
    r["ar_to_revenue"] = (ar / revenue) if (ar and revenue) else None
    r["cfo_to_ni"] = (cfo / ni) if (cfo and ni and ni != 0) else None
    r["accruals_ratio"] = ((ni - cfo) / total_assets) if (ni is not None and cfo is not None and total_assets) else None
    r["asset_turnover"] = (revenue / total_assets) if (revenue and total_assets) else None

    r["revenue_growth_yoy"] = None
    r["revenue_growth_qoq"] = None
    r["earnings_growth_yoy"] = None
    r["earnings_growth_qoq"] = None
    r["price_to_book"] = _safe(info.get("priceToBook"))

    r["updated_at"] = datetime.utcnow().isoformat()
    return r


def _fetch_info_with_retry(ticker: str, retries: int = 3) -> dict:
    import time
    for attempt in range(retries):
        try:
            info = yf.Ticker(ticker).info or {}
            if info:
                return info
        except Exception:
            pass
        time.sleep(2 ** attempt)  # 1s, 2s, 4s backoff
    return {}


_FUND_BATCH = 25  # reconnect every N tickers to avoid Neon idle-connection drops


def refresh_fundamentals(tickers: list[str]) -> dict:
    import time
    summary = {"updated": 0, "errors": []}

    for batch_start in range(0, len(tickers), _FUND_BATCH):
        batch = tickers[batch_start : batch_start + _FUND_BATCH]
        conn = get_conn()
        try:
            for ticker in batch:
                time.sleep(0.5)
                try:
                    yt = yf.Ticker(ticker)
                    info = _fetch_info_with_retry(ticker)
                    q_income = yt.quarterly_income_stmt
                    q_balance = yt.quarterly_balance_sheet
                    q_cashflow = yt.quarterly_cashflow
                    a_income = yt.income_stmt
                    a_balance = yt.balance_sheet
                    a_cashflow = yt.cashflow

                    periods_done = []

                    for df_set, ptype in [
                        ((q_income, q_balance, q_cashflow), "quarterly"),
                        ((a_income, a_balance, a_cashflow), "annual"),
                    ]:
                        inc, bal, cf = df_set
                        if inc is None or inc.empty:
                            continue
                        for col in inc.columns[:8]:
                            period_str = str(col)[:10]
                            try:
                                inc_p = inc[[col]] if col in inc.columns else pd.DataFrame()
                                bal_p = bal[[col]] if (bal is not None and col in bal.columns) else pd.DataFrame()
                                cf_p = cf[[col]] if (cf is not None and col in cf.columns) else pd.DataFrame()
                                row = _calc_ratios(info, inc_p, bal_p, cf_p, period_str, ptype)
                                row["ticker"] = ticker
                                _upsert_fundamentals(conn, row)
                                periods_done.append(period_str)
                            except Exception as e:
                                logger.debug("Ratio calc %s %s: %s", ticker, col, e)

                    if periods_done:
                        summary["updated"] += 1
                        conn.commit()
                        logger.debug("Fundamentals: %s — %d periods", ticker, len(periods_done))

                except Exception as e:
                    logger.warning("Fundamentals error %s: %s", ticker, e)
                    summary["errors"].append(f"{ticker}: {e}")
        finally:
            conn.close()

    return summary


def _upsert_fundamentals(conn, r: dict):
    cols = [
        "ticker", "period", "period_type",
        "roe", "roa", "gross_margin", "operating_margin", "net_margin",
        "revenue_growth_yoy", "revenue_growth_qoq",
        "earnings_growth_yoy", "earnings_growth_qoq",
        "debt_to_equity", "fcf_yield", "current_ratio",
        "ar_to_revenue", "cfo_to_ni", "accruals_ratio",
        "retained_earnings", "working_capital", "total_liabilities",
        "ebit", "rd_expense", "shares_outstanding",
        "dividends_paid", "buybacks", "asset_turnover",
        "revenue", "net_income", "cfo", "total_assets",
        "market_cap", "book_value", "ev", "ebitda",
        "forward_pe", "forward_eps", "price_to_book",
        "updated_at",
    ]
    vals = [r.get(c) for c in cols]
    placeholders = ",".join(["?"] * len(cols))
    conn.execute(
        f"INSERT OR REPLACE INTO fundamentals ({','.join(cols)}) VALUES ({placeholders})",
        vals,
    )


def get_fundamentals(conn, ticker: str, quarters: int = 8, period_type: str = "quarterly") -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT * FROM fundamentals WHERE ticker=? AND period_type=? "
        "ORDER BY period DESC LIMIT ?",
        conn, params=(ticker, period_type, quarters),
    )
    return df
