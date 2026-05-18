"""L5: Persistent risk state — JSON snapshot of all risk metrics."""
import json
import logging
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())

import sys as _sys; _sys.path.insert(0, str(ROOT))
from paths import cache_dir as _cache_dir  # noqa: E402
RISK_STATE_PATH = _cache_dir() / "risk_state.json"


def load() -> dict:
    if RISK_STATE_PATH.exists():
        try:
            return json.loads(RISK_STATE_PATH.read_text())
        except Exception:
            pass
    return _default_state()


def _default_state() -> dict:
    return {
        "daily_pnl": 0.0,
        "weekly_pnl": 0.0,
        "drawdown": 0.0,
        "peak_aum": _cfg["fund"]["aum_usd"],
        "current_aum": _cfg["fund"]["aum_usd"],
        "circuit_breaker_history": [],
        "factor_exposures": {},
        "risk_decomposition": {},
        "mctr": {},
        "alerts": [],
        "vix": 20.0,
        "credit_spread_zscore": None,
        "halt_active": False,
        "last_updated": None,
    }


def save(state: dict):
    RISK_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.utcnow().isoformat()
    RISK_STATE_PATH.write_text(json.dumps(state, indent=2, default=str))


def update_risk_state(
    portfolio_risk: dict,
    circuit_actions: list[dict],
    tail_actions: list[dict],
    stress_results: list[dict],
    vix: float,
    credit_spread_z: float | None,
):
    state = load()
    state["vix"] = vix
    state["credit_spread_zscore"] = credit_spread_z
    state["risk_decomposition"] = portfolio_risk
    state["mctr"] = portfolio_risk.get("mctr", {})
    state["halt_active"] = (ROOT / "cache" / "HALT.lock").exists()

    # Merge alerts
    alerts = state.get("alerts", [])
    now = datetime.utcnow().isoformat()
    for a in circuit_actions + tail_actions:
        alerts.insert(0, {**a, "ts": now})
    # Keep last 72 hours of alerts
    state["alerts"] = alerts[:50]

    state["stress_results"] = stress_results
    save(state)
    logger.info("Risk state updated")
