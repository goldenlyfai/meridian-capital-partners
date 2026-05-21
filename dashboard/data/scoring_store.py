"""Persist and load scored universe from the database."""
import logging
from datetime import datetime

import pandas as pd

from .db import get_conn

logger = logging.getLogger(__name__)

_FACTOR_COLS = [
    "composite", "momentum", "value", "quality", "growth",
    "estimate_revisions", "short_interest", "insider_activity", "institutional_flow",
]


def save_scores(scored: pd.DataFrame) -> int:
    """Upsert scored universe DataFrame into scored_universe table. Returns row count."""
    conn = get_conn()
    scored_at = datetime.utcnow().isoformat()
    rows = []
    for ticker, row in scored.iterrows():
        rows.append((
            str(ticker),
            str(row.get("company_name") or ""),
            str(row.get("sector") or ""),
            str(row.get("sub_industry") or ""),
            float(row.get("composite") or 50),
            float(row.get("momentum") or 50),
            float(row.get("value") or 50),
            float(row.get("quality") or 50),
            float(row.get("growth") or 50),
            float(row.get("estimate_revisions") or 50),
            float(row.get("short_interest") or 50),
            float(row.get("insider_activity") or 50),
            float(row.get("institutional_flow") or 50),
            str(row.get("signal") or "NEUTRAL"),
            scored_at,
        ))
    conn.executemany(
        """INSERT OR REPLACE INTO scored_universe
           (ticker, company_name, sector, sub_industry,
            composite, momentum, value, quality, growth,
            estimate_revisions, short_interest, insider_activity,
            institutional_flow, signal, scored_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    conn.close()
    logger.info("Saved %d scored tickers to DB", len(rows))
    return len(rows)


def load_scores() -> pd.DataFrame:
    """Load the latest scored universe from the database, sorted by composite desc."""
    conn = get_conn()
    df = pd.read_sql(
        """SELECT ticker, company_name, sector, sub_industry,
                  composite, momentum, value, quality, growth,
                  estimate_revisions, short_interest, insider_activity,
                  institutional_flow, signal, scored_at
           FROM scored_universe
           ORDER BY composite DESC""",
        conn,
    )
    conn.close()
    if not df.empty:
        df = df.set_index("ticker")
    return df
