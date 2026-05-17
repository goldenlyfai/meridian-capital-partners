"""L2: Insider Activity factor — 3 sub-factors."""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from data.db import get_conn
from data.sec_data import get_insider_transactions, detect_cluster_buying
from factors.utils import sector_percentile_rank, equal_weight_subscore, winsorize


def _net_flow(txns: list[dict], days: int = 90) -> float:
    """Net dollar flow: buys positive, sells negative. CEO/CFO weighted 3x."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    total = 0.0
    for t in txns:
        if t["date"] < cutoff:
            continue
        mult = 3.0 if t["is_ceo_cfo"] else 1.0
        amount = t.get("amount") or (t["shares"] * t["price"])
        if t["transaction_code"] == "P":
            total += amount * mult
        elif t["transaction_code"] == "S":
            total -= amount * mult
    return total


def compute_insider(universe_df: pd.DataFrame) -> pd.Series:
    conn = get_conn()
    tickers = universe_df["ticker"].tolist()
    sectors = universe_df.set_index("ticker")["sector"]

    records = {}
    for ticker in tickers:
        txns = get_insider_transactions(conn, ticker, days=90)
        if not txns:
            records[ticker] = {"net_flow": np.nan, "ceo_cfo_buy": 0.0, "cluster_buy": 0.0}
            continue

        net = _net_flow(txns)
        ceo_buy = sum(
            t.get("amount", t["shares"] * t["price"])
            for t in txns
            if t["is_ceo_cfo"] and t["transaction_code"] == "P"
        )
        cluster = 1.0 if detect_cluster_buying(conn, ticker) else 0.0

        records[ticker] = {
            "net_flow": net,
            "ceo_cfo_buy": ceo_buy,
            "cluster_buy": cluster,
        }

    conn.close()

    df = pd.DataFrame(records).T
    df.index.name = "ticker"
    sec = sectors.reindex(df.index)

    # Fill no-data tickers with sector median (50)
    ranked = {}
    for col in df.columns:
        s = winsorize(df[col].dropna().reindex(df.index))
        if s.dropna().empty:
            ranked[col] = pd.Series(50.0, index=df.index)
        else:
            r = sector_percentile_rank(s, sec)
            r = r.fillna(50.0)
            ranked[col] = r

    score = equal_weight_subscore(list(ranked.values()))
    score.name = "insider_activity"
    return score
