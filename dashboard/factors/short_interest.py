"""L2: Short Interest factor — 3 sub-factors."""
import numpy as np
import pandas as pd

from data.db import get_conn
from data.short_interest import get_short_interest, get_short_interest_change
from factors.utils import sector_percentile_rank, equal_weight_subscore, winsorize


def compute_short_interest(universe_df: pd.DataFrame, for_shorts: bool = False) -> pd.Series:
    """
    for_shorts=False (default): high short interest = BAD for longs.
    for_shorts=True: high/increasing short interest = GOOD (prime short candidates).
    """
    conn = get_conn()
    tickers = universe_df["ticker"].tolist()
    sectors = universe_df.set_index("ticker")["sector"]

    records = {}
    for ticker in tickers:
        si = get_short_interest(conn, ticker)
        chg = get_short_interest_change(conn, ticker)
        records[ticker] = {
            "short_pct_float": si.get("short_percent_float", np.nan),
            "days_to_cover": si.get("short_ratio", np.nan),
            "short_change": chg if chg is not None else np.nan,
        }

    conn.close()

    df = pd.DataFrame(records).T
    df.index.name = "ticker"
    sec = sectors.reindex(df.index)

    ranked = {}
    for col in df.columns:
        s = winsorize(df[col].dropna().reindex(df.index))
        r = sector_percentile_rank(s, sec)
        # For LONGS: lower short interest = better -> invert
        if not for_shorts:
            r = 100 - r
        ranked[col] = r

    score = equal_weight_subscore(list(ranked.values()))
    score.name = "short_interest"
    return score
