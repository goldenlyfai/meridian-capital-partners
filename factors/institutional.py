"""L2: Institutional Flow factor — 3 sub-factors."""
import numpy as np
import pandas as pd

from data.db import get_conn
from data.institutional import get_institutional_data
from factors.utils import sector_percentile_rank, equal_weight_subscore, winsorize


def compute_institutional(universe_df: pd.DataFrame) -> pd.Series:
    conn = get_conn()
    tickers = universe_df["ticker"].tolist()
    sectors = universe_df.set_index("ticker")["sector"]

    records = {}
    for ticker in tickers:
        data = get_institutional_data(conn, ticker)
        records[ticker] = {
            "num_funds": float(data.get("num_funds", 0)),
            "net_change": float(data.get("net_change", 0)),
            "multi_fund_open": 1.0 if data.get("multi_fund_open") else 0.0,
        }

    conn.close()

    df = pd.DataFrame(records).T
    df.index.name = "ticker"
    sec = sectors.reindex(df.index)

    ranked = {}
    for col in df.columns:
        s = winsorize(df[col].dropna().reindex(df.index))
        if s.dropna().empty:
            ranked[col] = pd.Series(50.0, index=df.index)
        else:
            ranked[col] = sector_percentile_rank(s, sec)

    score = equal_weight_subscore(list(ranked.values()))
    score.name = "institutional_flow"
    return score
