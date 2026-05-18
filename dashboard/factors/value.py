"""L2: Value factor — 6 sub-factors."""
import numpy as np
import pandas as pd

from data.db import get_conn
from data.fundamentals import get_fundamentals
from factors.utils import sector_percentile_rank, equal_weight_subscore, winsorize


def compute_value(universe_df: pd.DataFrame) -> pd.Series:
    conn = get_conn()
    tickers = universe_df["ticker"].tolist()
    sectors = universe_df.set_index("ticker")["sector"]

    records = {}
    for ticker in tickers:
        fund = get_fundamentals(conn, ticker, quarters=1, period_type="quarterly")
        if fund.empty:
            records[ticker] = {}
            continue
        r = fund.iloc[0]
        records[ticker] = {
            "fwd_earn_yield": (1 / r["forward_pe"]) if r.get("forward_pe") and r["forward_pe"] != 0 else np.nan,
            "book_to_price": (1 / r["price_to_book"]) if r.get("price_to_book") and r["price_to_book"] != 0 else np.nan,
            "fcf_yield": r.get("fcf_yield", np.nan),
            "ev_ebitda_inv": (1 / (r["ev"] / r["ebitda"])) if (r.get("ev") and r.get("ebitda") and r["ebitda"] != 0) else np.nan,
            "shareholder_yield": ((abs(r.get("buybacks") or 0) + abs(r.get("dividends_paid") or 0)) / r["market_cap"])
                                  if r.get("market_cap") and r["market_cap"] != 0 else np.nan,
            "sales_to_ev": (r["revenue"] / r["ev"]) if (r.get("revenue") and r.get("ev") and r["ev"] != 0) else np.nan,
        }

    conn.close()

    df = pd.DataFrame(records).T
    df.index.name = "ticker"
    sec = sectors.reindex(df.index)

    ranked = {}
    for col in df.columns:
        ranked[col] = sector_percentile_rank(winsorize(df[col].dropna().reindex(df.index)), sec)

    score = equal_weight_subscore(list(ranked.values()))
    score.name = "value"
    return score
