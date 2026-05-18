"""L2: Regime-conditional factor weights based on VIX level."""
import logging

import yaml
from pathlib import Path

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())


def get_vix_level() -> float:
    """Fetch latest VIX close from local DB."""
    try:
        from data.db import get_conn
        conn = get_conn()
        row = conn.execute(
            "SELECT close FROM daily_prices WHERE ticker='^VIX' ORDER BY date DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return float(row[0]) if row else 20.0
    except Exception:
        return 20.0


def get_weights(vix: float | None = None) -> dict[str, float]:
    """Return factor weights given current VIX regime."""
    if not _cfg["factors"].get("regime_conditional_weights", True):
        return dict(_cfg["factors"]["weights"])

    if vix is None:
        vix = get_vix_level()

    regimes = _cfg["factors"]["regimes"]

    if vix < 15:
        regime = "low_vol"
    elif vix > 25:
        regime = "high_vol"
    else:
        regime = "normal"

    weights = dict(regimes[regime])

    # Normalize to sum to 1
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    logger.info("Regime: %s (VIX=%.1f) — weights: %s", regime, vix, weights)
    return weights
