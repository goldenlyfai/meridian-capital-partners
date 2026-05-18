"""L5: Circuit breakers — fire on actual P&L losses."""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
cbcfg = _cfg["risk"]["circuit_breakers"]

import sys as _sys; _sys.path.insert(0, str(ROOT))
from paths import cache_dir as _cache_dir  # noqa: E402
RISK_STATE = _cache_dir() / "risk_state.json"
HALT_FILE = _cache_dir() / "HALT.lock"


def load_risk_state() -> dict:
    if RISK_STATE.exists():
        try:
            return json.loads(RISK_STATE.read_text())
        except Exception:
            pass
    return {"daily_pnl": 0.0, "weekly_pnl": 0.0, "peak_aum": 0.0, "current_aum": 0.0,
            "drawdown": 0.0, "circuit_breaker_history": [], "alerts": []}


def save_risk_state(state: dict):
    RISK_STATE.parent.mkdir(parents=True, exist_ok=True)
    RISK_STATE.write_text(json.dumps(state, indent=2, default=str))


def check_circuit_breakers(
    daily_pnl_pct: float,
    weekly_pnl_pct: float,
    drawdown_pct: float,
    aum: float,
) -> list[dict]:
    """
    Evaluate circuit breakers. Returns list of triggered actions.
    Actions: SIZE_DOWN, CLOSE_ALL_TODAY, KILL_SWITCH.
    """
    actions = []
    state = load_risk_state()
    now = datetime.utcnow().isoformat()

    # Daily > 1.5% -> SIZE_DOWN 30%
    if daily_pnl_pct < -cbcfg["daily_loss_size_down"]:
        action = {"type": "SIZE_DOWN", "reduction": cbcfg["size_down_reduction"],
                  "trigger": "daily_loss", "value": daily_pnl_pct, "ts": now}
        actions.append(action)
        logger.warning("CIRCUIT BREAKER: SIZE_DOWN 30%% — daily P&L %.2f%%", daily_pnl_pct * 100)

    # Daily > 2.5% -> CLOSE_ALL_TODAY
    if daily_pnl_pct < -cbcfg["daily_loss_close_all"]:
        action = {"type": "CLOSE_ALL_TODAY", "trigger": "daily_loss",
                  "value": daily_pnl_pct, "ts": now}
        actions.append(action)
        logger.critical("CIRCUIT BREAKER: CLOSE_ALL_TODAY — daily P&L %.2f%%", daily_pnl_pct * 100)

    # Weekly > 4% -> SIZE_DOWN 30%
    if weekly_pnl_pct < -cbcfg["weekly_loss_size_down"]:
        action = {"type": "SIZE_DOWN", "reduction": cbcfg["size_down_reduction"],
                  "trigger": "weekly_loss", "value": weekly_pnl_pct, "ts": now}
        actions.append(action)
        logger.warning("CIRCUIT BREAKER: SIZE_DOWN 30%% — weekly P&L %.2f%%", weekly_pnl_pct * 100)

    # Drawdown > 8% -> KILL_SWITCH
    if drawdown_pct < -cbcfg["drawdown_kill_switch"]:
        action = {"type": "KILL_SWITCH", "trigger": "drawdown",
                  "value": drawdown_pct, "ts": now}
        actions.append(action)
        HALT_FILE.parent.mkdir(parents=True, exist_ok=True)
        HALT_FILE.write_text(f"HALT activated at {now} — drawdown {drawdown_pct*100:.1f}%")
        logger.critical("KILL_SWITCH ACTIVATED — drawdown %.2f%% — halt lock written", drawdown_pct * 100)

    # Record to state
    for a in actions:
        state["circuit_breaker_history"].append(a)
    save_risk_state(state)

    return actions


def check_single_position(ticker: str, pnl_pct: float) -> bool:
    """Return True if position should be force-closed (>3% NAV loss)."""
    if pnl_pct < -cbcfg["single_position_force_close"]:
        logger.warning("FORCE CLOSE: %s — P&L %.2f%% exceeds limit", ticker, pnl_pct * 100)
        return True
    return False


def clear_halt():
    """Clear the KILL_SWITCH halt lock (--clear-halt)."""
    if HALT_FILE.exists():
        HALT_FILE.unlink()
        logger.info("HALT lock cleared")
    else:
        logger.info("No halt lock present")
