"""L2: Estimate Revisions factor — 3 sub-factors (30/60/90-day EPS deltas)."""
import numpy as np
import pandas as pd

from data.db import get_conn
from data.estimates import get_estimate_revisions
from factors.utils import sector_percentile_rank, equal_weight_subscore, winsorize


def compute_revisions(universe_df: pd.DataFrame) -> pd.Series:
    conn = get_conn()
    tickers = universe_df["ticker"].tolist()
    sectors = universe_df.set_index("ticker")["sector"]

    records = {}
    for ticker in tickers:
        revs = get_estimate_revisions(conn, ticker)
        records[ticker] = {
            "rev_30d": revs.get("rev_30d", np.nan),
            "rev_60d": revs.get("rev_60d", np.nan),
            "rev_90d": revs.get("rev_90d", np.nan),
        }

    conn.close()

    df = pd.DataFrame(records).T
    df.index.name = "ticker"
    sec = sectors.reindex(df.index)

    # Degenerate check: if all are NaN, return 50 for all
    if df.isnull().all().all():
        score = pd.Series(50.0, index=df.index, name="estimate_revisions")
        return score

    ranked = {}
    for col in df.columns:
        s = winsorize(df[col].dropna().reindex(df.index))
        if s.dropna().empty:
            ranked[col] = pd.Series(50.0, index=df.index)
        else:
            ranked[col] = sector_percentile_rank(s, sec)

    score = equal_weight_subscore(list(ranked.values()))
    score.name = "estimate_revisions"
    return score
