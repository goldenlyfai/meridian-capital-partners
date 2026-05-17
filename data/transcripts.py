"""L1-9: Earnings call transcripts via Financial Modeling Prep (optional)."""
import logging
import os
from datetime import datetime

import requests

from .db import get_conn

logger = logging.getLogger(__name__)

FMP_BASE = "https://financialmodelingprep.com/api/v3"


def refresh_transcripts(tickers: list[str]) -> dict:
    fmp_key = os.getenv("FMP_API_KEY")
    if not fmp_key:
        logger.info("FMP_API_KEY not set — skipping transcripts")
        return {"skipped": True, "reason": "no FMP_API_KEY"}

    conn = get_conn()
    summary = {"fetched": 0, "errors": []}

    for ticker in tickers:
        try:
            url = f"{FMP_BASE}/earning_call_transcript/{ticker}"
            r = requests.get(url, params={"apikey": fmp_key, "limit": 1}, timeout=30)
            r.raise_for_status()
            data = r.json()
            if not data:
                continue

            latest = data[0]
            quarter = f"Q{latest.get('quarter', '?')}"
            year = latest.get("year", 0)
            text = latest.get("content", "")
            if not text:
                continue

            conn.execute(
                """INSERT OR REPLACE INTO earnings_transcripts
                   (ticker, quarter, year, transcript, fetched_at)
                   VALUES (?,?,?,?,?)""",
                (ticker, f"{quarter}-{year}", year, text,
                 datetime.utcnow().isoformat()),
            )
            summary["fetched"] += 1

        except Exception as e:
            logger.debug("Transcript %s: %s", ticker, e)
            summary["errors"].append(f"{ticker}: {e}")

    conn.commit()
    conn.close()
    return summary


def get_transcript(conn, ticker: str) -> str | None:
    row = conn.execute(
        """SELECT transcript FROM earnings_transcripts
           WHERE ticker=? ORDER BY quarter DESC LIMIT 1""",
        (ticker,),
    ).fetchone()
    return row[0] if row else None
