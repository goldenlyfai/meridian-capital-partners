"""L3: Analysis result cache — SQLite with TTL eviction."""
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
TTL_DAYS = _cfg["analysis"]["cache_ttl_days"]

DB_PATH = ROOT / _cfg["database"]["path"]


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analysis_results (
            analyzer TEXT NOT NULL,
            ticker TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            result_json TEXT,
            created_at TEXT,
            PRIMARY KEY (analyzer, ticker, artifact_id)
        )
    """)
    conn.commit()
    return conn


def get_cached(analyzer: str, ticker: str, artifact_id: str) -> dict | None:
    conn = _get_conn()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=TTL_DAYS)).isoformat()
        row = conn.execute(
            """SELECT result_json, created_at FROM analysis_results
               WHERE analyzer=? AND ticker=? AND artifact_id=?
               AND created_at >= ?""",
            (analyzer, ticker, artifact_id, cutoff),
        ).fetchone()
        if row:
            logger.debug("Cache HIT: %s/%s/%s", analyzer, ticker, artifact_id)
            return json.loads(row[0])
        return None
    finally:
        conn.close()


def set_cached(analyzer: str, ticker: str, artifact_id: str, result: dict):
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO analysis_results
               (analyzer, ticker, artifact_id, result_json, created_at)
               VALUES (?,?,?,?,?)""",
            (analyzer, ticker, artifact_id, json.dumps(result),
             datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def evict_expired():
    conn = _get_conn()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=TTL_DAYS)).isoformat()
        n = conn.execute(
            "DELETE FROM analysis_results WHERE created_at < ?", (cutoff,)
        ).rowcount
        conn.commit()
        logger.info("Cache eviction: %d expired entries removed", n)
    finally:
        conn.close()
