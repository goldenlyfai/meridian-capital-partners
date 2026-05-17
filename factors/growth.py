"""L2: Growth factor — 5 sub-factors."""
import numpy as np
import pandas as pd

from data.db import get_conn
from data.fundamentals import get_fundamentals
from factors.utils import sector_percentile_rank, equal_weight_subscore, winsorize


def compute_growth(universe_df: pd.DataFrame) -> pd.Series:
    conn = get_conn()
    tickers = universe_df["ticker"].tolist()
    sectors = universe_df.set_index("ticker")["sector"]

    records = {}
    for ticker in tickers:
        fund = get_fundamentals(conn, ticker, quarters=8, period_type="quarterly")
        if fund.empty or len(fund) < 4:
            records[ticker] = {}
            continue
        r0, r4 = fund.iloc[0], fund.iloc[4] if len(fund) > 4 else fund.iloc[-1]

        def safe_yoy(col):
            v0 = r0.get(col)
            v4 = r4.get(col)
            if v0 is not None and v4 is not None and v4 != 0:
                return (float(v0) - float(v4)) / abs(float(v4))
            return np.nan

        # Revenue acceleration: latest YoY minus 4Q-ago YoY
        rev_growth_now = safe_yoy("revenue")
        r8 = fund.iloc[7] if len(fund) > 7 else None
        if r8 is not None and r4.get("revenue") and r8.get("revenue") and float(r8["revenue"]) != 0:
            rev_growth_prior = (float(r4["revenue"]) - float(r8["revenue"])) / abs(float(r8["revenue"]))
            rev_accel = (rev_growth_now - rev_growth_prior) if rev_growth_now is not None else np.nan
        else:
            rev_accel = np.nan

        # FCF growth
        fcf_now = (float(r0.get("cfo") or 0) + float(r0.get("asset_turnover") or 0))  # proxy
        # Actually compute from cfo
        cfo0 = r0.get("cfo")
        cfo4 = r4.get("cfo")
        fcf_growth = ((float(cfo0) - float(cfo4)) / abs(float(cfo4))) if (cfo0 and cfo4 and float(cfo4) != 0) else np.nan

        # R&D intensity
        rd_intensity = (float(r0.get("rd_expense") or 0) / float(r0.get("revenue"))) \
                       if (r0.get("rd_expense") and r0.get("revenue") and float(r0["revenue"]) != 0) else np.nan

        records[ticker] = {
            "revenue_growth_yoy": safe_yoy("revenue"),
            "earnings_growth_yoy": safe_yoy("net_income"),
            "revenue_accel": rev_accel,
            "rd_intensity": rd_intensity,
            "fcf_growth_yoy": fcf_growth,
        }

    conn.close()

    df = pd.DataFrame(records).T
    df.index.name = "ticker"
    sec = sectors.reindex(df.index)

    ranked = {}
    for col in df.columns:
        ranked[col] = sector_percentile_rank(winsorize(df[col].dropna().reindex(df.index)), sec)

    score = equal_weight_subscore(list(ranked.values()))
    score.name = "growth"
    return score
