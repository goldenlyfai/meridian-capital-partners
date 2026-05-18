"""L5: Tail risk monitor — VIX + credit spreads."""
import logging
import os

import pandas as pd

from data.db import get_conn

logger = logging.getLogger(__name__)


def get_vix() -> float:
    conn = get_conn()
    row = conn.execute(
        "SELECT close FROM daily_prices WHERE ticker='^VIX' ORDER BY date DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return float(row[0]) if row else 20.0


def get_credit_spread_zscore() -> float | None:
    """Fetch BAMLH0A0HYM2 from FRED if available; otherwise return None."""
    fred_key = os.getenv("FRED_API_KEY")
    if not fred_key:
        return None
    try:
        import requests
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": "BAMLH0A0HYM2",
            "api_key": fred_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 252,
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        vals = [float(o["value"]) for o in obs if o["value"] != "."]
        if not vals:
            return None
        series = pd.Series(vals)
        zscore = (vals[0] - series.mean()) / series.std()
        return float(zscore)
    except Exception as e:
        logger.debug("FRED credit spread: %s", e)
        return None


def evaluate_tail_risk(cfg: dict) -> list[dict]:
    """Return list of tail risk actions."""
    tcfg = cfg["risk"]["tail_risk"]
    vix = get_vix()
    cs_z = get_credit_spread_zscore()
    actions = []

    if vix >= tcfg["vix_reduce_50_threshold"]:
        actions.append({
            "type": "REDUCE_GROSS_50",
            "trigger": "VIX",
            "value": vix,
            "message": f"VIX={vix:.1f} >= {tcfg['vix_reduce_50_threshold']} — REDUCE GROSS 50%",
        })
        logger.critical("TAIL RISK: VIX %.1f — REDUCE GROSS 50%%", vix)
    elif vix >= tcfg["vix_reduce_20_threshold"]:
        actions.append({
            "type": "REDUCE_GROSS_20",
            "trigger": "VIX",
            "value": vix,
            "message": f"VIX={vix:.1f} >= {tcfg['vix_reduce_20_threshold']} — REDUCE GROSS 20%",
        })
        logger.warning("TAIL RISK: VIX %.1f — REDUCE GROSS 20%%", vix)

    if cs_z is not None and cs_z >= tcfg["credit_spread_zscore_threshold"]:
        actions.append({
            "type": "REDUCE_GROSS_20",
            "trigger": "credit_spread",
            "value": cs_z,
            "message": f"Credit spread z-score={cs_z:.2f} — REDUCE GROSS 20%",
        })
        logger.warning("TAIL RISK: Credit spread z=%.2f — REDUCE GROSS 20%%", cs_z)

    return actions
